#!/usr/bin/env python3
"""
Direct named-pose executor for Pepper.

Purpose:
- Make /pepper/moveit_named_goal move the real Pepper through /joint_angles.
- Bypass MoveIt trajectory planning for named joint targets.
- Use the same command names as the MoveIt SRDF states.

This is useful because Pepper's NAOqi ROS interface accepts JointAnglesWithSpeed,
while MoveIt normally expects a FollowJointTrajectory controller.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed

Pose = Tuple[List[str], List[float]]

NAMED_POSES: Dict[str, Pose] = {
    # Right arm
    "right_hand_up": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [-0.35, -0.45, 1.40, 0.85, 0.0],
    ),
    "right_up": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [-0.35, -0.45, 1.40, 0.85, 0.0],
    ),
    "right_arm_down": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [1.45, -0.15, 1.20, 0.50, 0.0],
    ),
    "right_down": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [1.45, -0.15, 1.20, 0.50, 0.0],
    ),
    "right_neutral": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [1.45, -0.15, 1.20, 0.50, 0.0],
    ),
    "right_present": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [0.65, -0.55, 1.10, 0.35, 0.0],
    ),
    "right_wave_start": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [-0.25, -0.55, 1.25, 0.90, -0.45],
    ),
    "right_wave_end": (
        ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
        [-0.25, -0.55, 1.25, 0.90, 0.45],
    ),

    # Left arm
    "left_hand_up": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [-0.35, 0.45, -1.40, -0.85, 0.0],
    ),
    "left_up": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [-0.35, 0.45, -1.40, -0.85, 0.0],
    ),
    "left_present": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [0.65, 0.55, -1.10, -0.35, 0.0],
    ),
    "left_arm_down": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [1.45, 0.15, -1.20, -0.50, 0.0],
    ),
    "left_down": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [1.45, 0.15, -1.20, -0.50, 0.0],
    ),
    "left_neutral": (
        ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw"],
        [1.45, 0.15, -1.20, -0.50, 0.0],
    ),

    # Both arms
    "neutral_arms": (
        [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
        ],
        [
            1.45, 0.15, -1.20, -0.50, 0.0,
            1.45, -0.15, 1.20, 0.50, 0.0,
        ],
    ),
    "both_arms_down": (
        [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
        ],
        [
            1.45, 0.15, -1.20, -0.50, 0.0,
            1.45, -0.15, 1.20, 0.50, 0.0,
        ],
    ),
    "both_down": (
        [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
        ],
        [
            1.45, 0.15, -1.20, -0.50, 0.0,
            1.45, -0.15, 1.20, 0.50, 0.0,
        ],
    ),
    "both_hands_up": (
        [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
        ],
        [
            -0.35, 0.45, -1.40, -0.85, 0.0,
            -0.35, -0.45, 1.40, 0.85, 0.0,
        ],
    ),
    "both_present": (
        [
            "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
            "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw",
        ],
        [
            0.65, 0.55, -1.10, -0.35, 0.0,
            0.65, -0.55, 1.10, 0.35, 0.0,
        ],
    ),
}


class PepperDirectNamedPoseExecutor(Node):
    def __init__(self):
        super().__init__("pepper_direct_named_pose_executor")

        self.declare_parameter("goal_topic", "/pepper/moveit_named_goal")
        self.declare_parameter("joint_command_topic", "/joint_angles")
        self.declare_parameter("allow_real_robot", False)
        self.declare_parameter("dry_run", True)
        self.declare_parameter("speed", 0.08)
        self.declare_parameter("publish_count", 3)
        self.declare_parameter("publish_period_sec", 0.20)

        self.goal_topic = self.get_parameter("goal_topic").value
        self.joint_command_topic = self.get_parameter("joint_command_topic").value
        self.allow_real_robot = bool(self.get_parameter("allow_real_robot").value)
        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.speed = float(self.get_parameter("speed").value)
        self.publish_count = int(self.get_parameter("publish_count").value)
        self.publish_period_sec = float(self.get_parameter("publish_period_sec").value)

        self.pub = self.create_publisher(JointAnglesWithSpeed, self.joint_command_topic, 10)
        self.sub = self.create_subscription(String, self.goal_topic, self.goal_callback, 10)

        self.get_logger().info("Pepper direct named-pose executor started.")
        self.get_logger().info(f"Subscribes: {self.goal_topic}")
        self.get_logger().info(f"Publishes:  {self.joint_command_topic}")
        self.get_logger().info(f"allow_real_robot={self.allow_real_robot}, dry_run={self.dry_run}")
        self.get_logger().info(f"Known targets: {sorted(NAMED_POSES.keys())}")

    def goal_callback(self, msg: String):
        target = msg.data.strip().lower()
        if not target:
            self.get_logger().warn("Ignored empty target.")
            return

        if target not in NAMED_POSES:
            self.get_logger().error(
                f"Unknown named pose: '{target}'. Known poses: {sorted(NAMED_POSES.keys())}"
            )
            return

        joint_names, joint_angles = NAMED_POSES[target]
        self.get_logger().info(f"Received target '{target}'.")
        self.get_logger().info(f"Command: {dict(zip(joint_names, [round(x, 4) for x in joint_angles]))}")

        if self.dry_run or not self.allow_real_robot:
            self.get_logger().warn("DRY RUN only. Not publishing to real Pepper.")
            return

        for i in range(max(1, self.publish_count)):
            out = JointAnglesWithSpeed()
            out.joint_names = list(joint_names)
            out.joint_angles = [float(v) for v in joint_angles]
            out.speed = float(self.speed)
            out.relative = 0
            self.pub.publish(out)
            self.get_logger().info(f"Published /joint_angles command {i + 1}/{self.publish_count} for '{target}'.")
            time.sleep(max(0.0, self.publish_period_sec))


def main(args=None):
    rclpy.init(args=args)
    node = PepperDirectNamedPoseExecutor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
