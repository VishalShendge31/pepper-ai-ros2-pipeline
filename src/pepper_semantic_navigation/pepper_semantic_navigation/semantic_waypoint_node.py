#!/usr/bin/env python3
import math
import os
import time
from typing import Dict, Any

import yaml
import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import tf2_ros


def quaternion_to_yaw(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def yaw_to_quaternion(yaw: float):
    half = yaw * 0.5
    return 0.0, 0.0, math.sin(half), math.cos(half)


class SemanticWaypointNode(Node):
    def __init__(self):
        super().__init__("semantic_waypoint_node")

        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_footprint")
        self.declare_parameter("vlm_topic", "/smolvlm/output")
        self.declare_parameter("save_place_topic", "/pepper/save_place")
        self.declare_parameter("go_to_place_topic", "/pepper/go_to_place")
        self.declare_parameter("status_topic", "/pepper/semantic_status")
        self.declare_parameter("waypoints_file", "~/pepper_ws/maps/pepper_waypoints.yaml")
        self.declare_parameter("navigate_action", "navigate_to_pose")

        self.map_frame = self.get_parameter("map_frame").value
        self.base_frame = self.get_parameter("base_frame").value
        self.vlm_topic = self.get_parameter("vlm_topic").value
        self.save_place_topic = self.get_parameter("save_place_topic").value
        self.go_to_place_topic = self.get_parameter("go_to_place_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.waypoints_file = os.path.expanduser(self.get_parameter("waypoints_file").value)
        self.navigate_action = self.get_parameter("navigate_action").value

        os.makedirs(os.path.dirname(self.waypoints_file), exist_ok=True)

        self.latest_vlm = ""
        self.latest_vlm_time = 0.0

        self.tf_buffer = tf2_ros.Buffer(cache_time=Duration(seconds=30.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.nav_client = ActionClient(self, NavigateToPose, self.navigate_action)

        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        self.create_subscription(String, self.vlm_topic, self.vlm_callback, 10)
        self.create_subscription(String, self.save_place_topic, self.save_place_callback, 10)
        self.create_subscription(String, self.go_to_place_topic, self.go_to_place_callback, 10)

        self.get_logger().info("SemanticWaypointNode ready.")
        self.get_logger().info(f"Waypoints file: {self.waypoints_file}")

    def publish_status(self, text: str):
        msg = String()
        msg.data = text
        self.status_pub.publish(msg)
        self.get_logger().info(text)

    def vlm_callback(self, msg: String):
        self.latest_vlm = msg.data.strip()
        self.latest_vlm_time = time.time()

    def load_waypoints(self) -> Dict[str, Any]:
        if not os.path.exists(self.waypoints_file):
            return {"places": {}}
        with open(self.waypoints_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("places", {})
        return data

    def save_waypoints(self, data: Dict[str, Any]):
        with open(self.waypoints_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=True, allow_unicode=True)

    def current_pose(self):
        transform = self.tf_buffer.lookup_transform(
            self.map_frame,
            self.base_frame,
            rclpy.time.Time(),
            timeout=Duration(seconds=1.0),
        )
        t = transform.transform.translation
        q = transform.transform.rotation
        yaw = quaternion_to_yaw(q.x, q.y, q.z, q.w)
        return {
            "x": float(t.x),
            "y": float(t.y),
            "z": float(t.z),
            "yaw": float(yaw),
            "frame_id": self.map_frame,
        }

    def save_place_callback(self, msg: String):
        name = msg.data.strip().lower().replace(" ", "_")
        if not name:
            self.publish_status("Save-place command ignored: empty name.")
            return

        try:
            pose = self.current_pose()
        except Exception as exc:
            self.publish_status(f"Failed to save '{name}': TF lookup failed: {exc}")
            return

        data = self.load_waypoints()
        data["places"][name] = {
            "pose": pose,
            "semantic_description": self.latest_vlm,
            "semantic_description_age_sec": (
                round(time.time() - self.latest_vlm_time, 2)
                if self.latest_vlm_time else None
            ),
            "updated_unix_time": time.time(),
        }
        self.save_waypoints(data)
        self.publish_status(
            f"Saved place '{name}' at x={pose['x']:.3f}, y={pose['y']:.3f}, yaw={pose['yaw']:.3f}"
        )

    def go_to_place_callback(self, msg: String):
        name = msg.data.strip().lower().replace(" ", "_")
        if not name:
            self.publish_status("Go-to-place command ignored: empty name.")
            return

        data = self.load_waypoints()
        place = data.get("places", {}).get(name)
        if place is None:
            known = ", ".join(sorted(data.get("places", {}).keys()))
            self.publish_status(f"Unknown place '{name}'. Known places: {known}")
            return

        pose = place["pose"]
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = pose.get("frame_id", self.map_frame)
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(pose["x"])
        goal.pose.pose.position.y = float(pose["y"])
        goal.pose.pose.position.z = 0.0

        qx, qy, qz, qw = yaw_to_quaternion(float(pose["yaw"]))
        goal.pose.pose.orientation.x = qx
        goal.pose.pose.orientation.y = qy
        goal.pose.pose.orientation.z = qz
        goal.pose.pose.orientation.w = qw

        if not self.nav_client.wait_for_server(timeout_sec=2.0):
            self.publish_status(
                f"Cannot navigate to '{name}': Nav2 action server '{self.navigate_action}' is not available."
            )
            return

        self.publish_status(f"Sending Nav2 goal for place '{name}'.")
        future = self.nav_client.send_goal_async(goal, feedback_callback=self.nav_feedback_callback)
        future.add_done_callback(lambda f: self.nav_goal_response_callback(f, name))

    def nav_goal_response_callback(self, future, name: str):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.publish_status(f"Navigation goal failed before acceptance: {exc}")
            return
        if not goal_handle.accepted:
            self.publish_status(f"Navigation goal to '{name}' was rejected.")
            return
        self.publish_status(f"Navigation goal to '{name}' accepted.")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda f: self.nav_result_callback(f, name))

    def nav_feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.publish_status(f"Navigation feedback: distance_remaining={feedback.distance_remaining:.2f} m")

    def nav_result_callback(self, future, name: str):
        try:
            result = future.result()
            self.publish_status(f"Navigation to '{name}' finished with status code {result.status}.")
        except Exception as exc:
            self.publish_status(f"Navigation to '{name}' result failed: {exc}")


def main(args=None):
    rclpy.init(args=args)
    node = SemanticWaypointNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
