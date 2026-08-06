#!/usr/bin/env python3
"""
Convert a MoveIt-planned JointTrajectory into Pepper /joint_angles commands.

This node is intentionally conservative:
- it does not execute unless allow_real_robot is true;
- it filters forbidden joints;
- it publishes absolute JointAnglesWithSpeed commands;
- it samples the planned trajectory point-by-point using the point timing.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Dict, List

import rclpy
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed


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

DEFAULT_FORBIDDEN_JOINTS = [
    "HeadYaw",
    "HeadPitch",
    "HipRoll",
    "HipPitch",
    "KneePitch",
]


class PepperTrajectoryExecutor(Node):
    def __init__(self):
        super().__init__("pepper_trajectory_executor")

        self.declare_parameter("trajectory_topic", "/pepper_moveit/planned_trajectory")
        self.declare_parameter("joint_command_topic", "/joint_angles")
        self.declare_parameter("allow_real_robot", False)
        self.declare_parameter("dry_run", True)
        self.declare_parameter("speed", 0.08)
        self.declare_parameter("min_point_dt_sec", 0.10)
        self.declare_parameter("max_point_dt_sec", 1.20)
        self.declare_parameter("allowed_joints", DEFAULT_ALLOWED_JOINTS)
        self.declare_parameter("forbidden_joints", DEFAULT_FORBIDDEN_JOINTS)
        self.declare_parameter("drop_empty_points", True)

        self.trajectory_topic = self.get_parameter("trajectory_topic").value
        self.joint_command_topic = self.get_parameter("joint_command_topic").value
        self.allow_real_robot = bool(self.get_parameter("allow_real_robot").value)
        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.speed = float(self.get_parameter("speed").value)
        self.min_point_dt_sec = float(self.get_parameter("min_point_dt_sec").value)
        self.max_point_dt_sec = float(self.get_parameter("max_point_dt_sec").value)
        self.allowed_joints = list(self.get_parameter("allowed_joints").value)
        self.forbidden_joints = set(self.get_parameter("forbidden_joints").value)
        self.drop_empty_points = bool(self.get_parameter("drop_empty_points").value)

        self.pub = self.create_publisher(JointAnglesWithSpeed, self.joint_command_topic, 10)
        self.sub = self.create_subscription(
            JointTrajectory,
            self.trajectory_topic,
            self.trajectory_callback,
            10,
        )

        self.execution_lock = threading.Lock()
        self.execution_thread = None
        self.cancel_requested = False

        self.get_logger().info("Pepper MoveIt trajectory executor started.")
        self.get_logger().info(f"Subscribes: {self.trajectory_topic}")
        self.get_logger().info(f"Publishes:  {self.joint_command_topic}")
        self.get_logger().info(f"allow_real_robot={self.allow_real_robot}, dry_run={self.dry_run}")
        self.get_logger().info(f"Allowed joints: {self.allowed_joints}")
        self.get_logger().info(f"Forbidden joints: {sorted(self.forbidden_joints)}")

    def trajectory_callback(self, msg: JointTrajectory):
        if not msg.joint_names:
            self.get_logger().warn("Ignored trajectory with no joint names.")
            return

        if not msg.points:
            self.get_logger().warn("Ignored trajectory with no points.")
            return

        with self.execution_lock:
            if self.execution_thread is not None and self.execution_thread.is_alive():
                self.cancel_requested = True
                self.execution_thread.join(timeout=1.0)

            self.cancel_requested = False
            self.execution_thread = threading.Thread(
                target=self.execute_trajectory,
                args=(msg,),
                daemon=True,
            )
            self.execution_thread.start()

    def execute_trajectory(self, traj: JointTrajectory):
        filtered_joint_indices = self.compute_filtered_joint_indices(traj.joint_names)

        if not filtered_joint_indices:
            self.get_logger().error("No executable joints remain after filtering.")
            return

        filtered_joint_names = [traj.joint_names[i] for i in filtered_joint_indices]

        self.get_logger().info(
            f"Executing planned trajectory: {len(filtered_joint_names)} joints, {len(traj.points)} points"
        )
        self.get_logger().info(f"Filtered joints: {filtered_joint_names}")

        previous_time = 0.0

        for point_index, point in enumerate(traj.points):
            if self.cancel_requested:
                self.get_logger().warn("Trajectory execution cancelled by newer trajectory.")
                return

            if len(point.positions) != len(traj.joint_names):
                self.get_logger().warn(
                    f"Skipping point {point_index}: positions length does not match joint_names length."
                )
                continue

            point_time = self.duration_to_sec(point.time_from_start)
            sleep_dt = point_time - previous_time
            previous_time = point_time

            if point_index > 0:
                sleep_dt = max(self.min_point_dt_sec, min(self.max_point_dt_sec, sleep_dt))
                time.sleep(sleep_dt)

            joint_angles = [float(point.positions[i]) for i in filtered_joint_indices]

            if not self.validate_angles(filtered_joint_names, joint_angles):
                self.get_logger().error(f"Invalid joint value detected at point {point_index}. Execution stopped.")
                return

            if self.dry_run or not self.allow_real_robot:
                self.get_logger().info(
                    f"DRY RUN point {point_index + 1}/{len(traj.points)}: "
                    f"{dict(zip(filtered_joint_names, [round(x, 4) for x in joint_angles]))}"
                )
                continue

            self.publish_joint_command(filtered_joint_names, joint_angles)

        self.get_logger().info("Trajectory execution finished.")

    def compute_filtered_joint_indices(self, joint_names: List[str]) -> List[int]:
        allowed_set = set(self.allowed_joints)
        indices = []

        for i, name in enumerate(joint_names):
            if name in self.forbidden_joints:
                self.get_logger().warn(f"Dropping forbidden joint from trajectory: {name}")
                continue

            if self.allowed_joints and name not in allowed_set:
                self.get_logger().warn(f"Dropping non-allowed joint from trajectory: {name}")
                continue

            indices.append(i)

        return indices

    @staticmethod
    def duration_to_sec(duration_msg) -> float:
        return float(duration_msg.sec) + float(duration_msg.nanosec) * 1e-9

    @staticmethod
    def validate_angles(joint_names: List[str], joint_angles: List[float]) -> bool:
        if len(joint_names) != len(joint_angles):
            return False

        for angle in joint_angles:
            if not math.isfinite(angle):
                return False
            if abs(angle) > 3.5:
                return False

        return True

    def publish_joint_command(self, joint_names: List[str], joint_angles: List[float]):
        msg = JointAnglesWithSpeed()
        msg.joint_names = list(joint_names)
        msg.joint_angles = [float(x) for x in joint_angles]
        msg.speed = self.speed

        if hasattr(msg, "relative"):
            msg.relative = False

        self.pub.publish(msg)

    def destroy_node(self):
        self.cancel_requested = True
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PepperTrajectoryExecutor()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
