#!/usr/bin/env python3

import json
import os
import sys
import termios
import tty
from datetime import datetime

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed


PEPPER_CONTROL_JOINTS = [
    "HeadYaw",
    "HeadPitch",

    "LShoulderPitch",
    "LShoulderRoll",
    "LElbowYaw",
    "LElbowRoll",
    "LWristYaw",

    "RShoulderPitch",
    "RShoulderRoll",
    "RElbowYaw",
    "RElbowRoll",
    "RWristYaw",

    "HipRoll",
    "HipPitch",
    "KneePitch"
]


class PepperActionRecorder(Node):
    def __init__(self):
        super().__init__("pepper_action_recorder")

        self.declare_parameter("joint_states_topic", "/joint_states")
        self.declare_parameter("output_file", "/home/robot/pepper_ws/src/pepper_social_skills/config/generated_pepper_actions.json")
        self.declare_parameter("send_to_real_pepper", False)
        self.declare_parameter("joint_command_topic", "/joint_angles")
        self.declare_parameter("default_speed", 0.10)
        self.declare_parameter("default_hold_sec", 1.0)

        self.joint_states_topic = self.get_parameter("joint_states_topic").value
        self.output_file = self.get_parameter("output_file").value
        self.send_to_real_pepper = bool(self.get_parameter("send_to_real_pepper").value)
        self.joint_command_topic = self.get_parameter("joint_command_topic").value
        self.default_speed = float(self.get_parameter("default_speed").value)
        self.default_hold_sec = float(self.get_parameter("default_hold_sec").value)

        self.current_joints = {}

        self.sub = self.create_subscription(
            JointState,
            self.joint_states_topic,
            self.joint_state_callback,
            10
        )

        self.pub = self.create_publisher(
            JointAnglesWithSpeed,
            self.joint_command_topic,
            10
        )

        self.timer = self.create_timer(0.05, self.keyboard_loop)

        self.get_logger().info("Pepper Action Recorder started.")
        self.get_logger().info("Move Pepper joints with joint_state_publisher_gui.")
        self.get_logger().info("Keyboard commands:")
        self.get_logger().info("  s = save current pose")
        self.get_logger().info("  p = publish current pose to real Pepper")
        self.get_logger().info("  q = quit")
        self.get_logger().info(f"Saving actions to: {self.output_file}")

    def joint_state_callback(self, msg):
        for name, position in zip(msg.name, msg.position):
            if name in PEPPER_CONTROL_JOINTS:
                self.current_joints[name] = float(position)

        if self.send_to_real_pepper:
            self.publish_current_pose()

    def publish_current_pose(self):
        if not self.current_joints:
            return

        joint_names = []
        joint_angles = []

        for joint in PEPPER_CONTROL_JOINTS:
            if joint in self.current_joints:
                joint_names.append(joint)
                joint_angles.append(self.current_joints[joint])

        msg = JointAnglesWithSpeed()
        msg.joint_names = joint_names
        msg.joint_angles = joint_angles
        msg.speed = self.default_speed

        if hasattr(msg, "relative"):
            msg.relative = False

        self.pub.publish(msg)

    def save_current_pose(self):
        if not self.current_joints:
            self.get_logger().warn("No joint values received yet.")
            return

        action_name = input("\nAction name: ").strip()

        if not action_name:
            self.get_logger().warn("Empty action name. Save cancelled.")
            return

        description = input("Description: ").strip()

        joint_names = []
        joint_angles = []

        for joint in PEPPER_CONTROL_JOINTS:
            if joint in self.current_joints:
                joint_names.append(joint)
                joint_angles.append(round(float(self.current_joints[joint]), 4))

        step = {
            "joint_names": joint_names,
            "joint_angles": joint_angles,
            "speed": self.default_speed,
            "hold_sec": self.default_hold_sec
        }

        action = {
            "description": description,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [step]
        }

        data = self.load_existing_file()
        data.setdefault("version", "generated")
        data.setdefault("description", "Generated Pepper actions from RViz joint slider poses.")
        data.setdefault("actions", {})
        data["actions"][action_name] = action

        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.get_logger().info(f"Saved action: {action_name}")

    def load_existing_file(self):
        if not os.path.exists(self.output_file):
            return {}

        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def keyboard_loop(self):
        if not sys.stdin.isatty():
            return

        key = self.get_key_nonblocking()

        if not key:
            return

        if key == "s":
            self.save_current_pose()

        elif key == "p":
            self.publish_current_pose()
            self.get_logger().info("Published current pose to real Pepper.")

        elif key == "q":
            self.get_logger().info("Quit requested.")
            rclpy.shutdown()

    def get_key_nonblocking(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            import select
            readable, _, _ = select.select([sys.stdin], [], [], 0.0)

            if readable:
                return sys.stdin.read(1)

            return None

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main(args=None):
    rclpy.init(args=args)
    node = PepperActionRecorder()

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
