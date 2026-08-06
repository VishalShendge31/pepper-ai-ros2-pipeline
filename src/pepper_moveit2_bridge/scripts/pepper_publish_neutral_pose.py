#!/usr/bin/env python3
"""
Publish a safe Pepper arms-down neutral pose once.

This is used before MoveIt trajectory execution so Pepper does not remain in the
all-zero URDF pose, where the arms appear forward. The node is conservative: it
only publishes to the real robot when allow_real_robot=true and dry_run=false.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed


NEUTRAL_ARM_JOINTS = [
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

NEUTRAL_ARM_ANGLES = [
    1.45,
    0.15,
    -1.20,
    -0.50,
    0.0,
    1.45,
    -0.15,
    1.20,
    0.50,
    0.0,
]


class PepperNeutralPosePublisher(Node):
    def __init__(self):
        super().__init__("pepper_neutral_pose_publisher")

        self.declare_parameter("joint_command_topic", "/joint_angles")
        self.declare_parameter("allow_real_robot", False)
        self.declare_parameter("dry_run", True)
        self.declare_parameter("delay_sec", 1.0)
        self.declare_parameter("speed", 0.06)
        self.declare_parameter("publish_count", 3)
        self.declare_parameter("publish_period_sec", 0.5)

        self.joint_command_topic = self.get_parameter("joint_command_topic").value
        self.allow_real_robot = bool(self.get_parameter("allow_real_robot").value)
        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.delay_sec = float(self.get_parameter("delay_sec").value)
        self.speed = float(self.get_parameter("speed").value)
        self.publish_count = int(self.get_parameter("publish_count").value)
        self.publish_period_sec = float(self.get_parameter("publish_period_sec").value)

        self.pub = self.create_publisher(JointAnglesWithSpeed, self.joint_command_topic, 10)
        self.timer = self.create_timer(max(0.1, self.delay_sec), self.publish_once_sequence)
        self.has_started = False

        self.get_logger().info("Pepper neutral arms-down publisher started.")
        self.get_logger().info(f"Topic: {self.joint_command_topic}")
        self.get_logger().info(f"allow_real_robot={self.allow_real_robot}, dry_run={self.dry_run}")

    def make_msg(self) -> JointAnglesWithSpeed:
        msg = JointAnglesWithSpeed()
        msg.joint_names = list(NEUTRAL_ARM_JOINTS)
        msg.joint_angles = [float(x) for x in NEUTRAL_ARM_ANGLES]
        msg.speed = float(self.speed)
        if hasattr(msg, "relative"):
            msg.relative = False
        return msg

    def publish_once_sequence(self):
        if self.has_started:
            return
        self.has_started = True
        self.timer.cancel()

        pose = dict(zip(NEUTRAL_ARM_JOINTS, NEUTRAL_ARM_ANGLES))

        if self.dry_run or not self.allow_real_robot:
            self.get_logger().info(f"DRY RUN neutral arms-down pose: {pose}")
            rclpy.shutdown()
            return

        msg = self.make_msg()
        for index in range(max(1, self.publish_count)):
            self.pub.publish(msg)
            self.get_logger().info(f"Published neutral arms-down pose {index + 1}/{self.publish_count}")
            time.sleep(max(0.05, self.publish_period_sec))

        rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    node = PepperNeutralPosePublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
