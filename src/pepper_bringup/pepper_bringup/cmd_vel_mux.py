#!/usr/bin/env python3
"""Priority cmd_vel multiplexer for Pepper.

Inputs (highest priority first):
  /cmd_vel_social  — safety stop / social manager
  /cmd_vel_teleop  — PS4 teleop
  /cmd_vel_nav     — Nav2 / autonomous

Output:
  /cmd_vel         — consumed by naoqi_driver

A source is active only while messages arrive within its timeout.
"""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


def twist_is_zero(twist: Twist, eps: float = 1e-6) -> bool:
    return (
        abs(twist.linear.x) < eps
        and abs(twist.linear.y) < eps
        and abs(twist.linear.z) < eps
        and abs(twist.angular.x) < eps
        and abs(twist.angular.y) < eps
        and abs(twist.angular.z) < eps
    )


class PepperCmdVelMux(Node):
    def __init__(self) -> None:
        super().__init__("pepper_cmd_vel_mux")

        self.declare_parameter("output_topic", "/cmd_vel")
        self.declare_parameter("teleop_topic", "/cmd_vel_teleop")
        self.declare_parameter("nav_topic", "/cmd_vel_nav")
        self.declare_parameter("social_topic", "/cmd_vel_social")
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("teleop_timeout_sec", 0.35)
        self.declare_parameter("nav_timeout_sec", 0.50)
        self.declare_parameter("social_timeout_sec", 0.75)
        self.declare_parameter("log_source_changes", True)

        self.output_topic = self.get_parameter("output_topic").value
        self.teleop_topic = self.get_parameter("teleop_topic").value
        self.nav_topic = self.get_parameter("nav_topic").value
        self.social_topic = self.get_parameter("social_topic").value
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.teleop_timeout_sec = float(self.get_parameter("teleop_timeout_sec").value)
        self.nav_timeout_sec = float(self.get_parameter("nav_timeout_sec").value)
        self.social_timeout_sec = float(self.get_parameter("social_timeout_sec").value)
        self.log_source_changes = bool(self.get_parameter("log_source_changes").value)

        self._sources = {
            "social": {"twist": Twist(), "stamp": 0.0, "timeout": self.social_timeout_sec},
            "teleop": {"twist": Twist(), "stamp": 0.0, "timeout": self.teleop_timeout_sec},
            "nav": {"twist": Twist(), "stamp": 0.0, "timeout": self.nav_timeout_sec},
        }
        self._active_source = "none"

        self.pub = self.create_publisher(Twist, self.output_topic, 10)
        self.create_subscription(Twist, self.social_topic, self._on_social, 10)
        self.create_subscription(Twist, self.teleop_topic, self._on_teleop, 10)
        self.create_subscription(Twist, self.nav_topic, self._on_nav, 10)

        period = 1.0 / max(1.0, self.publish_rate_hz)
        self.create_timer(period, self._publish)

        self.get_logger().info(
            f"cmd_vel mux: {self.social_topic} > {self.teleop_topic} > "
            f"{self.nav_topic} -> {self.output_topic}"
        )

    def _on_social(self, msg: Twist) -> None:
        self._sources["social"]["twist"] = msg
        self._sources["social"]["stamp"] = time.time()

    def _on_teleop(self, msg: Twist) -> None:
        self._sources["teleop"]["twist"] = msg
        self._sources["teleop"]["stamp"] = time.time()

    def _on_nav(self, msg: Twist) -> None:
        self._sources["nav"]["twist"] = msg
        self._sources["nav"]["stamp"] = time.time()

    def _active(self, name: str, now: float) -> bool:
        src = self._sources[name]
        return src["stamp"] > 0.0 and (now - src["stamp"]) <= src["timeout"]

    def _publish(self) -> None:
        now = time.time()
        selected = "none"
        twist = Twist()

        for name in ("social", "teleop", "nav"):
            if self._active(name, now):
                selected = name
                twist = self._sources[name]["twist"]
                break

        if selected != self._active_source:
            if self.log_source_changes:
                self.get_logger().info(f"cmd_vel source: {self._active_source} -> {selected}")
            self._active_source = selected

        # Always publish so the driver watchdog sees zeros when idle.
        self.pub.publish(twist)

        if selected == "none" and not twist_is_zero(twist):
            self.pub.publish(Twist())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PepperCmdVelMux()
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
