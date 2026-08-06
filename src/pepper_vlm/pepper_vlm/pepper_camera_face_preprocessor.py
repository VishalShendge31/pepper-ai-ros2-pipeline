#!/usr/bin/env python3

import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy
from sensor_msgs.msg import Image


class PepperCameraFacePreprocessor(Node):
    """Preprocess Pepper camera frames for the Face-API.js detection layer.

    This node replaces the older local-webcam perception_layer.py. It subscribes
    to Pepper's ROS camera topic and republishes a smaller, enhanced BGR image on
    /preprocessed_frames, which detection_layer.py already consumes.
    """

    def __init__(self):
        super().__init__("pepper_camera_face_preprocessor")

        self.declare_parameter("input_topic", "/camera/front/image_raw")
        self.declare_parameter("output_topic", "/preprocessed_frames")
        self.declare_parameter("publish_interval_sec", 0.20)  # max 5 FPS
        self.declare_parameter("target_width", 320)
        self.declare_parameter("target_height", 240)
        self.declare_parameter("enable_clahe", True)
        self.declare_parameter("enable_sharpening", True)
        self.declare_parameter("log_period_sec", 10.0)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.publish_interval_sec = float(self.get_parameter("publish_interval_sec").value)
        self.target_width = int(self.get_parameter("target_width").value)
        self.target_height = int(self.get_parameter("target_height").value)
        self.enable_clahe = bool(self.get_parameter("enable_clahe").value)
        self.enable_sharpening = bool(self.get_parameter("enable_sharpening").value)
        self.log_period_sec = float(self.get_parameter("log_period_sec").value)

        self.bridge = CvBridge()
        self.frame_count = 0
        self.published_count = 0
        self.last_publish_time = 0.0
        self.last_log_time = 0.0

        qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
        )

        self.sub = self.create_subscription(
            Image,
            self.input_topic,
            self.image_callback,
            qos,
        )

        self.pub = self.create_publisher(Image, self.output_topic, 1)

        self.get_logger().info("Pepper camera face preprocessor started.")
        self.get_logger().info(f"Input:  {self.input_topic}")
        self.get_logger().info(f"Output: {self.output_topic}")
        self.get_logger().info(
            f"Target: {self.target_width}x{self.target_height}, interval={self.publish_interval_sec:.2f}s"
        )

    def image_callback(self, msg: Image):
        now = time.time()
        self.frame_count += 1

        if now - self.last_publish_time < self.publish_interval_sec:
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            processed = self.preprocess_frame(frame)

            out = self.bridge.cv2_to_imgmsg(processed, encoding="bgr8")
            out.header = msg.header
            self.pub.publish(out)

            self.published_count += 1
            self.last_publish_time = now

            if now - self.last_log_time >= self.log_period_sec:
                h, w = processed.shape[:2]
                self.get_logger().info(
                    f"Preprocessed frames: received={self.frame_count}, published={self.published_count}, size={w}x{h}"
                )
                self.last_log_time = now

        except Exception as exc:
            self.get_logger().error(f"Face preprocessing failed: {exc}")

    def preprocess_frame(self, frame):
        height, width = frame.shape[:2]

        scale = min(self.target_width / max(1, width), self.target_height / max(1, height))
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

        # Put the resized frame on a fixed-size canvas. Stable dimensions make
        # downstream bounding boxes easier to interpret in the visualization node.
        canvas = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)
        x0 = (self.target_width - new_width) // 2
        y0 = (self.target_height - new_height) // 2
        canvas[y0:y0 + new_height, x0:x0 + new_width] = resized

        enhanced = canvas

        if self.enable_clahe:
            lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_channel = clahe.apply(l_channel)
            enhanced = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)

        if self.enable_sharpening:
            kernel = np.array([
                [0.0, -0.25, 0.0],
                [-0.25, 2.0, -0.25],
                [0.0, -0.25, 0.0],
            ], dtype=np.float32)
            enhanced = cv2.filter2D(enhanced, -1, kernel)

        return enhanced


def main(args=None):
    rclpy.init(args=args)
    node = PepperCameraFacePreprocessor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
