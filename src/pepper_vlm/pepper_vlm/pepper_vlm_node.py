#!/usr/bin/env python3

import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

import time
import torch
import rclpy

from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
from PIL import Image as PILImage
from transformers import AutoProcessor, AutoModelForImageTextToText
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class SmolVLMNode(Node):
    def __init__(self):
        super().__init__("smolvlm_node")

        self.declare_parameter("camera_topic", "/camera/front/image_raw")
        self.declare_parameter("output_topic", "/smolvlm/output")
        self.declare_parameter("process_interval_sec", 1.5)
        self.declare_parameter("model_name", "HuggingFaceTB/SmolVLM-500M-Instruct")

        self.camera_topic = self.get_parameter("camera_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.process_interval_sec = self.get_parameter("process_interval_sec").value
        self.model_name = self.get_parameter("model_name").value

        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            size={"longest_edge": 768},
        )

        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if DEVICE == "cuda" else torch.float32,
        ).to(DEVICE)

        self.bridge = CvBridge()

        qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
        )

        self.sub = self.create_subscription(
            Image,
            self.camera_topic,
            self.image_callback,
            qos,
        )

        self.pub = self.create_publisher(String, self.output_topic, 10)

        self.is_processing = False
        self.last_process_time = 0.0

        self.get_logger().info(f"VLM camera input: {self.camera_topic}")
        self.get_logger().info(f"VLM output: {self.output_topic}")

    def image_callback(self, msg):
        now = time.time()

        if self.is_processing:
            return

        if now - self.last_process_time < self.process_interval_sec:
            return

        self.is_processing = True
        self.last_process_time = now

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            pil_image = PILImage.fromarray(cv_image[:, :, ::-1])

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {
                            "type": "text",
                            "text": (
                                "Describe the robot camera image concisely. "
                                "Mention people, objects, visible gestures, and emotion. "
                                "If someone is waving, explicitly say: someone is waving."
                            ),
                        },
                    ],
                }
            ]

            prompt = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
            )

            inputs = self.processor(
                text=prompt,
                images=[pil_image],
                return_tensors="pt",
            ).to(DEVICE)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=80,
                    do_sample=False,
                )

            text = self.processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
            )[0]

            text = self.extract_answer(text)

            out = String()
            out.data = text
            self.pub.publish(out)

            self.get_logger().info(f"VLM: {text}")

        except Exception as e:
            self.get_logger().error(f"VLM processing failed: {e}")

        finally:
            self.is_processing = False

    def extract_answer(self, text):
        for marker in ["Assistant:", "ASSISTANT:", "assistant:"]:
            if marker in text:
                return text.split(marker)[-1].strip()
        return text.strip()


def main(args=None):
    rclpy.init(args=args)
    node = SmolVLMNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
