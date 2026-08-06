#!/usr/bin/env python3
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class PepperLaserFilter(Node):
    def __init__(self):
        super().__init__("pepper_laser_filter")
        self.declare_parameter("input_topic", "/laser")
        self.declare_parameter("output_topic", "/scan_clean")
        self.declare_parameter("range_min", 0.10)
        self.declare_parameter("range_max", 3.00)
        self.declare_parameter("use_current_time", True)

        self.input_topic = self.get_parameter("input_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.range_min = float(self.get_parameter("range_min").value)
        self.range_max = float(self.get_parameter("range_max").value)
        self.use_current_time = bool(self.get_parameter("use_current_time").value)

        self.pub = self.create_publisher(LaserScan, self.output_topic, 10)
        self.sub = self.create_subscription(LaserScan, self.input_topic, self.callback, 10)

        self.get_logger().info(f"Filtering {self.input_topic} -> {self.output_topic}")
        self.get_logger().info(f"Valid range: {self.range_min:.2f} m to {self.range_max:.2f} m")
        self.get_logger().info(f"use_current_time: {self.use_current_time}")

    def callback(self, msg: LaserScan):
        cleaned = []
        for r in msg.ranges:
            if not math.isfinite(r) or r < self.range_min or r > self.range_max:
                cleaned.append(float("inf"))
            else:
                cleaned.append(float(r))

        if not cleaned:
            return

        out = LaserScan()
        out.header.frame_id = msg.header.frame_id
        out.header.stamp = self.get_clock().now().to_msg() if self.use_current_time else msg.header.stamp
        out.angle_min = msg.angle_min
        out.angle_increment = msg.angle_increment

        # Critical Pepper fix: compute angle_max from actual beam count.
        out.angle_max = out.angle_min + out.angle_increment * (len(cleaned) - 1)

        out.time_increment = 0.0
        out.scan_time = 0.0
        out.range_min = self.range_min
        out.range_max = self.range_max
        out.ranges = cleaned
        out.intensities = []
        self.pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = PepperLaserFilter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
