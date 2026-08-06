#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String


class PepperSystemMonitor(Node):
    def __init__(self):
        super().__init__('pepper_system_monitor')
        self.declare_parameter('check_period_sec', 5.0)
        self.declare_parameter('required_topics', [
            '/audio',
            '/camera/front/image_raw',
            '/whisper_transcript',
            '/openai_response',
            '/speech',
            '/cmd_vel',
            '/joy',
            '/pepper/animation_command',
            '/pepper/animation_status',
        ])
        self.required_topics = list(self.get_parameter('required_topics').value)
        self.pub = self.create_publisher(String, '/pepper/system_monitor', 10)
        period = float(self.get_parameter('check_period_sec').value)
        self.create_timer(period, self.check_topics)
        self.get_logger().info('Pepper system monitor started.')

    def check_topics(self):
        available = {name for name, _types in self.get_topic_names_and_types()}
        missing = [topic for topic in self.required_topics if topic not in available]
        if missing:
            text = 'missing_topics: ' + ', '.join(missing)
            self.get_logger().warn(text)
        else:
            text = 'all_required_topics_available'
            self.get_logger().info(text)
        msg = String()
        msg.data = text
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PepperSystemMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
