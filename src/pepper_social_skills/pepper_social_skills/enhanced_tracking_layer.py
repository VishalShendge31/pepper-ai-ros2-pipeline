#!/usr/bin/env python3

import json
import math
import time
from collections import defaultdict

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class FaceTracker(Node):
    def __init__(self):
        super().__init__("enhanced_tracking_layer")

        self.declare_parameter("input_topic", "/face_detections")
        self.declare_parameter("output_topic", "/recognized_faces")
        self.declare_parameter("embedding_threshold", 0.60)
        self.declare_parameter("position_threshold", 100.0)
        self.declare_parameter("timeout_seconds", 30.0)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.embedding_threshold = float(self.get_parameter("embedding_threshold").value)
        self.position_threshold = float(self.get_parameter("position_threshold").value)
        self.timeout_seconds = float(self.get_parameter("timeout_seconds").value)

        self.known_faces = {}
        self.next_face_id = 1
        self.position_history = defaultdict(list)

        self.sub = self.create_subscription(
            String,
            self.input_topic,
            self.detection_callback,
            10,
        )

        self.pub = self.create_publisher(
            String,
            self.output_topic,
            10,
        )

        self.timer = self.create_timer(5.0, self.cleanup_old_faces)

        self.get_logger().info("Enhanced face tracking layer started.")
        self.get_logger().info(f"Subscribes: {self.input_topic}")
        self.get_logger().info(f"Publishes:  {self.output_topic}")

    def detection_callback(self, msg):
        try:
            detection_data = json.loads(msg.data)
            current_faces = detection_data.get("faces", [])
            current_time = time.time()

            embeddings = []
            for face in current_faces:
                emb = face.get("embedding")
                if emb and len(emb) == 128:
                    arr = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    embeddings.append(arr / norm if norm > 0 else None)
                else:
                    embeddings.append(None)

            matched_ids = set()
            tracked_faces = []

            for i, face in enumerate(current_faces):
                best_id = None
                best_score = 0.0

                if embeddings[i] is not None:
                    for face_id, stored in self.known_faces.items():
                        if face_id in matched_ids:
                            continue

                        stored_emb = stored.get("embedding")
                        if stored_emb is None:
                            continue

                        sim = float(np.dot(embeddings[i], stored_emb))
                        pos_score = self.position_score(
                            stored.get("last_position", [0.0, 0.0]),
                            face.get("bounding_box", {}),
                        )
                        score = 0.8 * sim + 0.2 * pos_score

                        if score > best_score and score >= self.embedding_threshold:
                            best_score = score
                            best_id = face_id

                if best_id is None:
                    best_id = self.next_face_id
                    self.next_face_id += 1
                    self.add_face(best_id, face, current_time, embeddings[i])
                    is_new = True
                else:
                    self.update_face(best_id, face, current_time, embeddings[i])
                    matched_ids.add(best_id)
                    is_new = False

                tracked_faces.append(self.make_output_face(best_id, face, is_new))

            output = {
                "timestamp": current_time,
                "source_frame_number": detection_data.get("frame_number", 0),
                "faces_detected": len(tracked_faces),
                "faces": tracked_faces,
            }

            out = String()
            out.data = json.dumps(output, ensure_ascii=False)
            self.pub.publish(out)

        except Exception as exc:
            self.get_logger().error(f"Tracking error: {exc}")

    def box_center(self, box):
        return [
            float(box.get("x", 0.0)) + float(box.get("width", 0.0)) / 2.0,
            float(box.get("y", 0.0)) + float(box.get("height", 0.0)) / 2.0,
        ]

    def position_score(self, old_center, box):
        if not old_center or not box:
            return 0.0

        new_center = self.box_center(box)
        dist = math.sqrt(
            (new_center[0] - old_center[0]) ** 2 +
            (new_center[1] - old_center[1]) ** 2
        )
        return max(0.0, 1.0 - dist / self.position_threshold)

    def add_face(self, face_id, face, timestamp, embedding):
        center = self.box_center(face.get("bounding_box", {}))

        self.known_faces[face_id] = {
            "first_seen": timestamp,
            "last_seen": timestamp,
            "appearances": 1,
            "age": face.get("age", 0),
            "gender": face.get("gender", "unknown"),
            "dominant_expression": face.get("dominant_expression", "neutral"),
            "bounding_box": face.get("bounding_box", {}),
            "last_position": center,
            "embedding": embedding,
            "confidence": face.get("detection_confidence", face.get("confidence", 0.5)),
        }

    def update_face(self, face_id, face, timestamp, embedding):
        record = self.known_faces[face_id]
        record["last_seen"] = timestamp
        record["appearances"] += 1

        age = face.get("age", 0)
        if age:
            old_age = record.get("age", age)
            record["age"] = int(0.7 * old_age + 0.3 * age)

        if face.get("gender_confidence", 0.0) > 0.7:
            record["gender"] = face.get("gender", record.get("gender", "unknown"))

        record["dominant_expression"] = face.get(
            "dominant_expression",
            record.get("dominant_expression", "neutral"),
        )
        record["bounding_box"] = face.get("bounding_box", record.get("bounding_box", {}))
        record["last_position"] = self.box_center(record["bounding_box"])
        record["confidence"] = face.get(
            "detection_confidence",
            face.get("confidence", record.get("confidence", 0.5)),
        )

        if embedding is not None:
            old_emb = record.get("embedding")
            if old_emb is not None:
                mixed = 0.8 * old_emb + 0.2 * embedding
                norm = np.linalg.norm(mixed)
                record["embedding"] = mixed / norm if norm > 0 else embedding
            else:
                record["embedding"] = embedding

    def make_output_face(self, face_id, face, is_new=False):
        record = self.known_faces.get(face_id, {})

        return {
            "user_id": f"user_{face_id}",
            "is_new": is_new,
            "appearances": record.get("appearances", 1),
            "age": record.get("age", face.get("age", 0)),
            "gender": record.get("gender", face.get("gender", "unknown")),
            "dominant_expression": record.get(
                "dominant_expression",
                face.get("dominant_expression", "neutral"),
            ),
            "confidence": record.get(
                "confidence",
                face.get("detection_confidence", face.get("confidence", 0.5)),
            ),
            "bounding_box": record.get("bounding_box", face.get("bounding_box", {})),
            "last_seen": record.get("last_seen", time.time()),
        }

    def cleanup_old_faces(self):
        now = time.time()
        stale = [
            fid for fid, data in self.known_faces.items()
            if now - data.get("last_seen", now) > self.timeout_seconds
        ]

        for fid in stale:
            del self.known_faces[fid]
            self.get_logger().info(f"Removed stale face user_{fid}")


def main(args=None):
    rclpy.init(args=args)
    node = FaceTracker()
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
