#!/usr/bin/env python3

import json
import math
import os
import random
import re
import time
from collections import deque

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed


class PepperGestureNode(Node):
    def __init__(self):
        super().__init__("pepper_gesture_node")

        self.declare_parameter("vlm_topic", "/smolvlm/output")
        self.declare_parameter("response_topic", "/openai_response")
        self.declare_parameter("joint_topic", "/joint_angles")
        self.declare_parameter("actions_file", "")

        self.declare_parameter("enable_wave_from_camera", True)
        self.declare_parameter("enable_vlm_keyword_actions", True)
        self.declare_parameter("enable_response_keyword_actions", True)
        self.declare_parameter("enable_speech_gestures", True)

        self.declare_parameter("wave_cooldown_sec", 8.0)
        self.declare_parameter("speech_gesture_cooldown_sec", 1.8)
        self.declare_parameter("event_gesture_cooldown_sec", 4.0)

        self.declare_parameter("min_speech_gesture_sec", 2.0)
        self.declare_parameter("max_speech_gesture_sec", 10.0)
        self.declare_parameter("speech_words_per_sec", 2.2)

        self.declare_parameter("randomize_speech_actions", False)

        self.vlm_topic = self.get_parameter("vlm_topic").value
        self.response_topic = self.get_parameter("response_topic").value
        self.joint_topic = self.get_parameter("joint_topic").value
        self.actions_file = self.get_parameter("actions_file").value

        self.enable_wave_from_camera = bool(
            self.get_parameter("enable_wave_from_camera").value
        )
        self.enable_vlm_keyword_actions = bool(
            self.get_parameter("enable_vlm_keyword_actions").value
        )
        self.enable_response_keyword_actions = bool(
            self.get_parameter("enable_response_keyword_actions").value
        )
        self.enable_speech_gestures = bool(
            self.get_parameter("enable_speech_gestures").value
        )

        self.wave_cooldown_sec = float(self.get_parameter("wave_cooldown_sec").value)
        self.speech_gesture_cooldown_sec = float(
            self.get_parameter("speech_gesture_cooldown_sec").value
        )
        self.event_gesture_cooldown_sec = float(
            self.get_parameter("event_gesture_cooldown_sec").value
        )

        self.min_speech_gesture_sec = float(
            self.get_parameter("min_speech_gesture_sec").value
        )
        self.max_speech_gesture_sec = float(
            self.get_parameter("max_speech_gesture_sec").value
        )
        self.speech_words_per_sec = float(
            self.get_parameter("speech_words_per_sec").value
        )

        self.randomize_speech_actions = bool(
            self.get_parameter("randomize_speech_actions").value
        )

        self.action_config = self.load_action_config(self.actions_file)
        self.triggers = self.action_config.get("triggers", {})
        self.actions = self.action_config.get("actions", {})

        self.wave_keywords = self.triggers.get("vlm_wave_keywords", [])
        self.wave_action = self.triggers.get("wave_action", "wave_right_hand_smooth")
        self.speech_action = self.triggers.get("speech_action", "speech_explain_smooth")
        self.speech_actions = self.triggers.get("speech_actions", [self.speech_action])
        self.neutral_action = self.triggers.get("neutral_action", "neutral_both_arms")
        self.response_keyword_actions = self.triggers.get("response_keyword_actions", {})
        self.vlm_keyword_actions = self.triggers.get("vlm_keyword_actions", {})

        self.pub_joints = self.create_publisher(
            JointAnglesWithSpeed,
            self.joint_topic,
            10,
        )

        self.pub_gesture_event = self.create_publisher(
            String,
            "/social_skill/gesture",
            10,
        )

        self.sub_vlm = self.create_subscription(
            String,
            self.vlm_topic,
            self.vlm_callback,
            10,
        )

        self.sub_response = self.create_subscription(
            String,
            self.response_topic,
            self.response_callback,
            10,
        )

        self.sequence = deque()
        self.is_running_sequence = False

        self.last_wave_time = 0.0
        self.last_speech_gesture_time = 0.0
        self.last_event_gesture_time = 0.0
        self.speech_action_index = 0

        self.sequence_timer = self.create_timer(0.10, self.sequence_timer_callback)

        self.get_logger().info("Pepper arm gesture node started.")
        self.get_logger().info("Head and neck control is disabled in this node.")
        self.get_logger().info(f"Actions file: {self.actions_file}")
        self.get_logger().info(f"Available actions: {list(self.actions.keys())}")
        self.get_logger().info(f"Speech action loop: {self.speech_actions}")
        self.get_logger().info(f"VLM topic: {self.vlm_topic}")
        self.get_logger().info(f"Response topic: {self.response_topic}")
        self.get_logger().info(f"Joint command topic: {self.joint_topic}")

        time.sleep(0.5)
        self.publish_action_once(self.neutral_action)

    def load_action_config(self, path: str):
        if not path:
            raise RuntimeError(
                "actions_file parameter is empty. Provide pepper_actions.json in the launch file."
            )

        expanded_path = os.path.expanduser(path)

        if not os.path.exists(expanded_path):
            raise RuntimeError(f"Action file does not exist: {expanded_path}")

        with open(expanded_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if "actions" not in data:
            raise RuntimeError("Invalid action JSON: missing top-level 'actions' field.")

        return data

    def normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\säöüß?]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def publish_gesture_event(self, event: str):
        msg = String()
        msg.data = event
        self.pub_gesture_event.publish(msg)
        self.get_logger().info(f"Gesture event: {event}")

    def extract_vlm_field(self, vlm_text: str, field_name: str) -> str:
        pattern = rf"(?im)^\s*{field_name}\s*[:\-]\s*(.+?)\s*$"
        match = re.search(pattern, vlm_text or "")

        if not match:
            return ""

        return match.group(1).strip()

    def parse_vlm_context(self, vlm_text: str) -> dict:
        person = self.extract_vlm_field(vlm_text, "PERSON").lower().strip().replace(" ", "_")
        gesture = self.extract_vlm_field(vlm_text, "GESTURE").lower().strip().replace(" ", "_")
        emotion = self.extract_vlm_field(vlm_text, "EMOTION").lower().strip().replace(" ", "_")
        scene = self.extract_vlm_field(vlm_text, "SCENE").strip()

        if person in ["yes", "visible", "person_visible"]:
            person = "unknown"
        elif person in ["no", "not_visible", "no_person", "none_visible"]:
            person = "none"

        if not person:
            person = "none"
        if not gesture:
            gesture = "none" if person == "none" else "unknown"
        if not emotion:
            emotion = "unknown"

        return {
            "person": person,
            "gesture": gesture,
            "emotion": emotion,
            "scene": scene,
        }

    def detect_wave_from_vlm(self, vlm_text: str) -> bool:
        ctx = self.parse_vlm_context(vlm_text)
        gesture = ctx["gesture"]

        # The physical response is a greeting wave. Trigger it only for wave-like
        # camera observations, not for arbitrary gestures such as sitting or holding_object.
        wave_like_gestures = [
            "waving",
            "wave",
            "raised_hand",
            "hand_raised",
            "hand_up",
            "open_palm",
        ]

        if gesture in wave_like_gestures:
            return True

        normalized_text = self.normalize(vlm_text)

        for keyword in self.wave_keywords:
            if self.normalize(keyword) in normalized_text:
                return True

        german_patterns = [
            "geste winken",
            "geste winkt",
            "person winkt",
            "jemand winkt",
            "hand hoch",
            "gehobene hand",
            "hand gehoben",
        ]

        for pattern in german_patterns:
            if self.normalize(pattern) in normalized_text:
                return True

        return False

    def find_keyword_action(self, normalized_text: str, mapping: dict):
        for keyword, action_name in mapping.items():
            normalized_keyword = self.normalize(str(keyword))

            if not normalized_keyword:
                continue

            if normalized_keyword == "?":
                if "?" in normalized_text:
                    return action_name
                continue

            if normalized_keyword in normalized_text:
                return action_name

        return None

    def vlm_callback(self, msg: String):
        text = msg.data.strip()
        if not text:
            return

        normalized = self.normalize(text)
        ctx = self.parse_vlm_context(text)
        normalized_structured = self.normalize(
            f"person {ctx['person']} gesture {ctx['gesture']} emotion {ctx['emotion']} scene {ctx['scene']}"
        )
        self.get_logger().info(f"VLM received for gesture detection: {text}")

        now = time.time()

        if self.enable_vlm_keyword_actions:
            action_name = self.find_keyword_action(normalized_structured, self.vlm_keyword_actions)
            if action_name is None:
                action_name = self.find_keyword_action(normalized, self.vlm_keyword_actions)

            if action_name:
                if now - self.last_event_gesture_time < self.event_gesture_cooldown_sec:
                    return
                if self.is_running_sequence:
                    return

                self.last_event_gesture_time = now
                self.publish_gesture_event(f"trigger:vlm_keyword -> action:{action_name}")
                self.enqueue_action(action_name)
                return

        if not self.enable_wave_from_camera:
            return

        wave_detected = self.detect_wave_from_vlm(text)
        self.get_logger().info(f"Wave or raised-hand trigger detected: {wave_detected}")

        if not wave_detected:
            return

        if now - self.last_wave_time < self.wave_cooldown_sec:
            return

        if self.is_running_sequence:
            return

        self.last_wave_time = now
        self.publish_gesture_event(f"trigger:vlm_wave_or_raised_hand -> action:{self.wave_action}")
        self.enqueue_action(self.wave_action)

    def response_callback(self, msg: String):
        text = msg.data.strip()
        if not text:
            return

        normalized = self.normalize(text)
        now = time.time()

        if self.enable_response_keyword_actions:
            keyword_action = self.find_keyword_action(normalized, self.response_keyword_actions)

            if keyword_action and not self.is_running_sequence:
                if now - self.last_event_gesture_time >= self.event_gesture_cooldown_sec:
                    self.last_event_gesture_time = now
                    self.publish_gesture_event(
                        f"trigger:response_keyword -> action:{keyword_action}"
                    )
                    self.enqueue_action(keyword_action)
                    return

        if not self.enable_speech_gestures:
            return

        if now - self.last_speech_gesture_time < self.speech_gesture_cooldown_sec:
            return

        if self.is_running_sequence:
            return

        self.last_speech_gesture_time = now

        duration = self.estimate_speech_duration(text)
        planned_actions = self.plan_speech_actions(duration)

        self.publish_gesture_event(
            f"trigger:speech_response -> actions:{planned_actions}, target_duration:{duration:.2f}s"
        )

        self.enqueue_action_list(planned_actions)

    def estimate_speech_duration(self, text: str) -> float:
        words = len(text.split())

        if self.speech_words_per_sec <= 0.0:
            self.speech_words_per_sec = 2.2

        duration = words / self.speech_words_per_sec
        duration = max(self.min_speech_gesture_sec, duration)
        duration = min(self.max_speech_gesture_sec, duration)

        return duration

    def action_duration(self, action_name: str) -> float:
        action = self.actions.get(action_name)
        if not action:
            return 0.0

        return sum(float(step.get("hold_sec", 0.3)) for step in action.get("steps", []))

    def plan_speech_actions(self, target_duration_sec: float):
        valid_actions = [name for name in self.speech_actions if name in self.actions]

        if not valid_actions:
            valid_actions = [self.speech_action]

        planned = []
        accumulated = 0.0
        guard = 0

        while accumulated < target_duration_sec and guard < 12:
            if self.randomize_speech_actions:
                action_name = random.choice(valid_actions)
            else:
                action_name = valid_actions[self.speech_action_index % len(valid_actions)]
                self.speech_action_index += 1

            planned.append(action_name)
            accumulated += max(0.3, self.action_duration(action_name))
            guard += 1

        if not planned:
            planned = [self.speech_action]

        if self.neutral_action in self.actions:
            planned.append(self.neutral_action)

        return planned

    def compute_repeat_count(self, action_name: str, target_duration_sec: float) -> int:
        action = self.actions.get(action_name)

        if not action:
            return 1

        if not action.get("repeatable", False):
            return 1

        steps = action.get("steps", [])
        one_cycle_sec = sum(float(step.get("hold_sec", 0.3)) for step in steps)

        if one_cycle_sec <= 0.0:
            return 1

        repeat_count = int(math.ceil(target_duration_sec / one_cycle_sec))
        repeat_count = max(1, repeat_count)
        repeat_count = min(5, repeat_count)

        return repeat_count

    def validate_step(self, action_name: str, step: dict):
        required = ["joint_names", "joint_angles", "speed", "hold_sec"]

        for key in required:
            if key not in step:
                raise RuntimeError(
                    f"Action '{action_name}' has invalid step. Missing key: {key}"
                )

        joint_names = step["joint_names"]
        joint_angles = step["joint_angles"]

        if len(joint_names) != len(joint_angles):
            raise RuntimeError(
                f"Action '{action_name}' has mismatched joint_names and joint_angles length."
            )

        forbidden_head_joints = ["HeadYaw", "HeadPitch"]

        for joint_name in joint_names:
            if joint_name in forbidden_head_joints:
                raise RuntimeError(
                    f"Action '{action_name}' contains forbidden head/neck joint: {joint_name}"
                )

    def enqueue_action_list(self, action_names):
        self.clear_sequence()

        for action_name in action_names:
            self.append_action_to_sequence(action_name)

    def enqueue_action(self, action_name: str, repeat_count: int = 1):
        self.clear_sequence()

        repeat_count = max(1, int(repeat_count))
        for _ in range(repeat_count):
            self.append_action_to_sequence(action_name)

    def append_action_to_sequence(self, action_name: str):
        if action_name not in self.actions:
            self.get_logger().error(f"Unknown action requested: {action_name}")
            return

        action = self.actions[action_name]
        steps = action.get("steps", [])

        if not steps:
            self.get_logger().warn(f"Action '{action_name}' has no steps.")
            return

        for step in steps:
            self.validate_step(action_name, step)
            self.enqueue_pose(
                step["joint_names"],
                step["joint_angles"],
                float(step["speed"]),
                float(step["hold_sec"]),
                action_name,
            )

        finish_action = action.get("finish_action", None)

        if finish_action:
            finish = self.actions.get(finish_action)
            if not finish:
                self.get_logger().error(
                    f"Action '{action_name}' has unknown finish_action: {finish_action}"
                )
                return

            for step in finish.get("steps", []):
                self.validate_step(finish_action, step)
                self.enqueue_pose(
                    step["joint_names"],
                    step["joint_angles"],
                    float(step["speed"]),
                    float(step["hold_sec"]),
                    finish_action,
                )

    def publish_action_once(self, action_name: str):
        action = self.actions.get(action_name)

        if not action:
            self.get_logger().error(f"Unknown action requested: {action_name}")
            return

        steps = action.get("steps", [])

        for step in steps:
            self.validate_step(action_name, step)
            self.publish_joints(
                step["joint_names"],
                step["joint_angles"],
                float(step["speed"]),
            )

    def enqueue_pose(
        self,
        joint_names,
        joint_angles,
        speed: float,
        hold_sec: float,
        action_name: str,
    ):
        self.sequence.append(
            {
                "action_name": action_name,
                "joint_names": list(joint_names),
                "joint_angles": [float(angle) for angle in joint_angles],
                "speed": float(speed),
                "hold_sec": float(hold_sec),
                "sent": False,
                "sent_time": 0.0,
            }
        )

    def sequence_timer_callback(self):
        if not self.sequence:
            self.is_running_sequence = False
            return

        self.is_running_sequence = True
        current = self.sequence[0]
        now = time.time()

        if not current["sent"]:
            self.publish_joints(
                current["joint_names"],
                current["joint_angles"],
                current["speed"],
            )
            current["sent"] = True
            current["sent_time"] = now
            return

        if now - current["sent_time"] >= current["hold_sec"]:
            self.sequence.popleft()

    def make_joint_msg(self, joint_names, joint_angles, speed):
        msg = JointAnglesWithSpeed()
        msg.joint_names = list(joint_names)
        msg.joint_angles = [float(angle) for angle in joint_angles]
        msg.speed = float(speed)

        if hasattr(msg, "relative"):
            try:
                msg.relative = False
            except Exception:
                msg.relative = 0

        return msg

    def publish_joints(self, joint_names, joint_angles, speed):
        msg = self.make_joint_msg(joint_names, joint_angles, speed)
        self.pub_joints.publish(msg)

    def clear_sequence(self):
        self.sequence.clear()
        self.is_running_sequence = False

    def destroy_node(self):
        try:
            self.clear_sequence()
            self.publish_action_once(self.neutral_action)
        except Exception:
            pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PepperGestureNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
