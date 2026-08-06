#!/usr/bin/env python3

import json
import os
import signal
import subprocess
import tempfile
import threading
import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


class DetectionLayer(Node):
    """Run Face-API.js on preprocessed ROS image frames.

    Input:  /preprocessed_frames sensor_msgs/Image
    Output: /face_detections std_msgs/String JSON

    The JavaScript detector path is parameterized so the node can run inside the
    existing Pepper workspace instead of depending on a fixed /home/pepper path.
    """

    def __init__(self):
        super().__init__("detection_layer")

        self.declare_parameter("input_topic", "/preprocessed_frames")
        self.declare_parameter("output_topic", "/face_detections")
        self.declare_parameter("faceapi_path", os.path.expanduser("~/face-api-project"))
        self.declare_parameter("pipeline_script", "final-pipeline.js")
        self.declare_parameter("min_frame_interval", 20.0)
        self.declare_parameter("detection_timeout_sec", 25.0)
        self.declare_parameter("target_width", 256)
        self.declare_parameter("target_height", 192)
        self.declare_parameter("jpeg_quality", 60)
        self.declare_parameter("publish_empty_on_failure", True)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.faceapi_path = os.path.expanduser(self.get_parameter("faceapi_path").value)
        pipeline_script_param = os.path.expanduser(self.get_parameter("pipeline_script").value)
        self.min_frame_interval = float(self.get_parameter("min_frame_interval").value)
        self.detection_timeout = float(self.get_parameter("detection_timeout_sec").value)
        self.target_width = int(self.get_parameter("target_width").value)
        self.target_height = int(self.get_parameter("target_height").value)
        self.jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self.publish_empty_on_failure = bool(self.get_parameter("publish_empty_on_failure").value)

        if os.path.isabs(pipeline_script_param):
            self.pipeline_script = pipeline_script_param
        else:
            self.pipeline_script = os.path.join(self.faceapi_path, pipeline_script_param)

        if not os.path.exists(self.pipeline_script):
            raise FileNotFoundError(
                f"Face-API pipeline script not found: {self.pipeline_script}. "
                "Set detection_layer parameter faceapi_path or pipeline_script."
            )

        self.bridge = CvBridge()
        self.processing = False
        self.current_frame = None
        self.frame_count = 0
        self.last_processing_time = 0.0
        self.successful_detections = 0
        self.failed_detections = 0

        self.frame_subscriber = self.create_subscription(
            Image,
            self.input_topic,
            self.frame_callback,
            1,
        )
        self.detection_publisher = self.create_publisher(String, self.output_topic, 10)
        self.status_timer = self.create_timer(10.0, self.status_callback)

        self.get_logger().info("Face detection layer started.")
        self.get_logger().info(f"Input: {self.input_topic}")
        self.get_logger().info(f"Output: {self.output_topic}")
        self.get_logger().info(f"Face-API path: {self.faceapi_path}")
        self.get_logger().info(f"Pipeline script: {self.pipeline_script}")
        self.get_logger().info(f"Timeout={self.detection_timeout:.1f}s, interval={self.min_frame_interval:.1f}s")

    def frame_callback(self, msg: Image):
        if self.processing:
            return

        current_time = time.time()
        if current_time - self.last_processing_time < self.min_frame_interval:
            return

        try:
            self.current_frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.frame_count += 1
            self.processing = True
            self.last_processing_time = current_time

            thread = threading.Thread(target=self.process_frame, daemon=True)
            thread.start()

        except Exception as exc:
            self.get_logger().error(f"Frame callback failed: {exc}")
            self.processing = False

    def process_frame(self):
        temp_file = None
        start_time = time.time()

        try:
            if self.current_frame is None:
                return

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp:
                temp_file = temp.name

            resized = self.resize_for_detection(self.current_frame)
            cv2.imwrite(
                temp_file,
                resized,
                [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, self.jpeg_quality))],
            )

            h, w = resized.shape[:2]
            self.get_logger().info(f"Running face detection for frame {self.frame_count} ({w}x{h})")

            process = subprocess.Popen(
                ["node", self.pipeline_script, temp_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.faceapi_path,
                preexec_fn=os.setsid,
            )

            try:
                stdout, stderr = process.communicate(timeout=self.detection_timeout)
            except subprocess.TimeoutExpired:
                self.failed_detections += 1
                self.get_logger().warning(f"Face detection timed out after {self.detection_timeout:.1f}s")
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception:
                    pass
                process.wait()
                if self.publish_empty_on_failure:
                    self.publish_detections(self.empty_detection(start_time, reason="timeout"))
                return

            if process.returncode != 0:
                self.failed_detections += 1
                err = (stderr or stdout or "").strip()[:500]
                self.get_logger().warning(f"Face detection process failed: {err}")
                if self.publish_empty_on_failure:
                    self.publish_detections(self.empty_detection(start_time, reason="process_failed"))
                return

            detection_data = self.parse_output(stdout, start_time)
            self.successful_detections += 1
            self.publish_detections(detection_data)

        except Exception as exc:
            self.failed_detections += 1
            self.get_logger().error(f"Processing failed: {exc}")
            if self.publish_empty_on_failure:
                self.publish_detections(self.empty_detection(start_time, reason=str(exc)))

        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            self.processing = False

    def resize_for_detection(self, frame):
        height, width = frame.shape[:2]
        if width <= self.target_width and height <= self.target_height:
            return frame

        scale = min(self.target_width / max(1, width), self.target_height / max(1, height))
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    def parse_output(self, output: str, start_time: float):
        if "===JSON_START===" in output and "===JSON_END===" in output:
            json_part = output.split("===JSON_START===", 1)[1].split("===JSON_END===", 1)[0].strip()
            try:
                json_data = json.loads(json_part)
                faces = [self.normalize_face(face) for face in json_data.get("faces", [])]
                return {
                    "timestamp": start_time,
                    "processing_time": time.time() - start_time,
                    "frame_number": self.frame_count,
                    "faces_detected": len(faces),
                    "faces": faces,
                    "source": "face_api_json",
                }
            except json.JSONDecodeError as exc:
                self.get_logger().warning(f"JSON parse failed, falling back to text parser: {exc}")

        faces = self.parse_text_output(output)
        return {
            "timestamp": start_time,
            "processing_time": time.time() - start_time,
            "frame_number": self.frame_count,
            "faces_detected": len(faces),
            "faces": faces,
            "source": "face_api_text",
        }

    def normalize_face(self, face):
        face = dict(face or {})

        if "embedding" not in face:
            for key in ["descriptor", "face_descriptor", "recognition_embedding"]:
                if key in face:
                    face["embedding"] = face[key]
                    break

        embedding = face.get("embedding")
        if not isinstance(embedding, list) or len(embedding) != 128:
            face["embedding"] = self.generate_synthetic_embedding(face)

        face.setdefault("age", 0)
        face.setdefault("gender", "unknown")
        face.setdefault("gender_confidence", 0.0)
        face.setdefault("dominant_expression", "neutral")
        face.setdefault("expression_confidence", 0.0)
        face.setdefault("detection_confidence", face.get("confidence", 0.5))
        face.setdefault("bounding_box", {"x": 0, "y": 0, "width": 0, "height": 0})
        return face

    def parse_text_output(self, output: str):
        faces = []
        current_face = {}

        for raw_line in output.strip().split("\n"):
            line = raw_line.strip()

            if line.startswith("--- Face"):
                if current_face:
                    faces.append(self.normalize_face(current_face))
                current_face = {}
                continue

            if line.startswith("Age:"):
                try:
                    age_text = line.split(":", 1)[1].strip()
                    current_face["age"] = int(float(age_text.split()[0]))
                except Exception:
                    current_face["age"] = 0
                continue

            if line.startswith("Gender:"):
                try:
                    gender_text = line.split(":", 1)[1].strip()
                    if "(" in gender_text:
                        label, conf = gender_text.split("(", 1)
                        current_face["gender"] = label.strip()
                        current_face["gender_confidence"] = float(conf.split("%", 1)[0].strip()) / 100.0
                    else:
                        current_face["gender"] = gender_text
                        current_face["gender_confidence"] = 0.5
                except Exception:
                    current_face["gender"] = "unknown"
                    current_face["gender_confidence"] = 0.0
                continue

            if line.startswith("Expression:"):
                try:
                    expr_text = line.split(":", 1)[1].strip()
                    if "(" in expr_text:
                        label, conf = expr_text.split("(", 1)
                        current_face["dominant_expression"] = label.strip()
                        current_face["expression_confidence"] = float(conf.split("%", 1)[0].strip()) / 100.0
                    else:
                        current_face["dominant_expression"] = expr_text
                        current_face["expression_confidence"] = 0.5
                except Exception:
                    current_face["dominant_expression"] = "neutral"
                    current_face["expression_confidence"] = 0.0
                continue

            if line.startswith("Position:"):
                try:
                    pos_text = line.split(":", 1)[1].strip()
                    box = {}
                    for part in pos_text.split(","):
                        if "=" not in part:
                            continue
                        key, value = part.split("=", 1)
                        box[key.strip()] = int(float(value.strip()))
                    current_face["bounding_box"] = box
                except Exception:
                    current_face["bounding_box"] = {"x": 0, "y": 0, "width": 0, "height": 0}
                continue

            if line.startswith("Confidence:"):
                try:
                    conf_text = line.split(":", 1)[1].strip().replace("%", "")
                    current_face["detection_confidence"] = float(conf_text) / 100.0
                except Exception:
                    current_face["detection_confidence"] = 0.0

        if current_face:
            faces.append(self.normalize_face(current_face))

        return faces

    def generate_synthetic_embedding(self, face_data):
        """Fallback embedding when the JS pipeline does not provide a descriptor.

        This is only for weak frame-to-frame association. Real face recognition
        requires the 128D Face-API descriptor from the JavaScript pipeline.
        """
        embedding = np.zeros(128, dtype=np.float32)
        age = face_data.get("age", 30) or 30
        embedding[0] = min(float(age) / 100.0, 1.0)

        gender = str(face_data.get("gender", "unknown")).lower()
        if "female" in gender:
            embedding[1] = -1.0
        elif "male" in gender:
            embedding[1] = 1.0

        expression = str(face_data.get("dominant_expression", "neutral")).lower()
        expr_map = {"happy": 0.2, "sad": 0.4, "angry": 0.6, "surprised": 0.8, "neutral": 0.0}
        embedding[2] = expr_map.get(expression, 0.0)

        box = face_data.get("bounding_box", {}) or {}
        seed = int(box.get("x", 0)) + int(box.get("y", 0)) + int(self.frame_count)
        rng = np.random.default_rng(seed % 10000)
        embedding[10:50] = rng.normal(0.0, 0.1, 40)

        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.tolist()

    def empty_detection(self, start_time: float, reason: str = ""):
        return {
            "timestamp": start_time,
            "processing_time": time.time() - start_time,
            "frame_number": self.frame_count,
            "faces_detected": 0,
            "faces": [],
            "source": "face_api_error",
            "error": reason,
        }

    def publish_detections(self, detection_data):
        msg = String()
        msg.data = json.dumps(detection_data, ensure_ascii=False, default=str)
        self.detection_publisher.publish(msg)

        count = int(detection_data.get("faces_detected", 0))
        if count > 0:
            self.get_logger().info(f"Published {count} detected face(s)")
        else:
            self.get_logger().info("Published no-face detection result")

    def status_callback(self):
        attempts = self.successful_detections + self.failed_detections
        success_rate = (self.successful_detections / max(1, attempts)) * 100.0
        self.get_logger().info(
            "Face detection stats: "
            f"frames={self.frame_count}, ok={self.successful_detections}, "
            f"failed={self.failed_detections}, success={success_rate:.1f}%, "
            f"state={'processing' if self.processing else 'idle'}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DetectionLayer()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
