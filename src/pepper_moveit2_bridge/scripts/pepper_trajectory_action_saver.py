#!/usr/bin/env python3
"""
Save the latest MoveIt JointTrajectory as a Pepper social-skill JSON action.

Usage:
  1. Plan a trajectory with MoveIt.
  2. Publish the planned JointTrajectory to /pepper_moveit/planned_trajectory.
  3. Save it:
       ros2 topic pub --once /pepper_moveit/save_action std_msgs/msg/String "data: 'moveit_wave_right'"
"""

from __future__ import annotations

import json
import os
import time
from typing import List

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectory


DEFAULT_ALLOWED_JOINTS = [
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
]


class PepperTrajectoryActionSaver(Node):
    def __init__(self):
        super().__init__("pepper_trajectory_action_saver")

        self.declare_parameter("trajectory_topic", "/pepper_moveit/planned_trajectory")
        self.declare_parameter("save_topic", "/pepper_moveit/save_action")
        self.declare_parameter(
            "actions_file",
            "/home/robot/pepper_ws/src/pepper_social_skills/config/generated_moveit_actions.json",
        )
        self.declare_parameter("allowed_joints", DEFAULT_ALLOWED_JOINTS)
        self.declare_parameter("default_speed", 0.08)
        self.declare_parameter("min_hold_sec", 0.15)
        self.declare_parameter("max_hold_sec", 1.20)
        self.declare_parameter("description_prefix", "Generated from MoveIt 2 planned trajectory")

        self.trajectory_topic = self.get_parameter("trajectory_topic").value
        self.save_topic = self.get_parameter("save_topic").value
        self.actions_file = os.path.expanduser(self.get_parameter("actions_file").value)
        self.allowed_joints = list(self.get_parameter("allowed_joints").value)
        self.default_speed = float(self.get_parameter("default_speed").value)
        self.min_hold_sec = float(self.get_parameter("min_hold_sec").value)
        self.max_hold_sec = float(self.get_parameter("max_hold_sec").value)
        self.description_prefix = self.get_parameter("description_prefix").value

        self.latest_trajectory = None

        self.create_subscription(JointTrajectory, self.trajectory_topic, self.trajectory_callback, 10)
        self.create_subscription(String, self.save_topic, self.save_callback, 10)

        self.get_logger().info("Pepper MoveIt action saver started.")
        self.get_logger().info(f"Latest trajectory input: {self.trajectory_topic}")
        self.get_logger().info(f"Save trigger topic:       {self.save_topic}")
        self.get_logger().info(f"Actions file:             {self.actions_file}")

    def trajectory_callback(self, msg: JointTrajectory):
        self.latest_trajectory = msg
        self.get_logger().info(
            f"Stored latest trajectory: {len(msg.joint_names)} joints, {len(msg.points)} points"
        )

    def save_callback(self, msg: String):
        action_name = msg.data.strip().lower().replace(" ", "_")

        if not action_name:
            self.get_logger().warn("Ignored save request with empty action name.")
            return

        if self.latest_trajectory is None:
            self.get_logger().warn("No trajectory received yet. Nothing to save.")
            return

        action = self.convert_trajectory_to_action(self.latest_trajectory, action_name)
        if action is None:
            return

        data = self.load_actions_file()
        data.setdefault("version", "generated_moveit2")
        data.setdefault("description", "Generated Pepper actions from MoveIt 2 trajectories.")
        data.setdefault("actions", {})
        data["actions"][action_name] = action

        os.makedirs(os.path.dirname(self.actions_file), exist_ok=True)
        with open(self.actions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.get_logger().info(f"Saved MoveIt action '{action_name}' to {self.actions_file}")

    def convert_trajectory_to_action(self, traj: JointTrajectory, action_name: str):
        if not traj.joint_names or not traj.points:
            self.get_logger().warn("Trajectory is empty. Cannot save action.")
            return None

        indices = [
            i for i, name in enumerate(traj.joint_names)
            if name in set(self.allowed_joints)
        ]

        if not indices:
            self.get_logger().warn("No allowed Pepper arm joints in trajectory. Cannot save action.")
            return None

        filtered_names = [traj.joint_names[i] for i in indices]
        steps = []
        previous_time = 0.0

        for point in traj.points:
            if len(point.positions) != len(traj.joint_names):
                continue

            current_time = self.duration_to_sec(point.time_from_start)
            hold_sec = current_time - previous_time
            previous_time = current_time

            if hold_sec <= 0.0:
                hold_sec = self.min_hold_sec

            hold_sec = max(self.min_hold_sec, min(self.max_hold_sec, hold_sec))

            step = {
                "joint_names": filtered_names,
                "joint_angles": [round(float(point.positions[i]), 4) for i in indices],
                "speed": self.default_speed,
                "hold_sec": round(float(hold_sec), 3),
            }
            steps.append(step)

        if not steps:
            self.get_logger().warn("No valid trajectory points converted. Cannot save action.")
            return None

        return {
            "description": f"{self.description_prefix}: {action_name}",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "repeatable": False,
            "steps": steps,
        }

    def load_actions_file(self):
        if not os.path.exists(self.actions_file):
            return {}

        try:
            with open(self.actions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.get_logger().warn(f"Could not read existing actions file. Starting new file. Error: {exc}")
            return {}

    @staticmethod
    def duration_to_sec(duration_msg) -> float:
        return float(duration_msg.sec) + float(duration_msg.nanosec) * 1e-9


def main(args=None):
    rclpy.init(args=args)
    node = PepperTrajectoryActionSaver()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
