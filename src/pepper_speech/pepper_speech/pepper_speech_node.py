#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class PepperSpeechNode(Node):
    def __init__(self):
        super().__init__("pepper_speech_node")

        self.declare_parameter("input_topic", "/openai_response")
        self.declare_parameter("speech_topic", "/speech")

        self.input_topic = self.get_parameter("input_topic").value
        self.speech_topic = self.get_parameter("speech_topic").value

        self.sub = self.create_subscription(
            String,
            self.input_topic,
            self.response_callback,
            10,
        )

        self.pub = self.create_publisher(
            String,
            self.speech_topic,
            10,
        )

        self.get_logger().info(f"Listening to LLM response: {self.input_topic}")
        self.get_logger().info(f"Publishing speech text to Pepper: {self.speech_topic}")

    def response_callback(self, msg):
        text = msg.data.strip()

        if not text:
            self.get_logger().warn("Empty response received")
            return

        out = String()
        out.data = text
        self.pub.publish(out)

        self.get_logger().info(f"Sent to Pepper speech: {text}")


def main(args=None):
    rclpy.init(args=args)
    node = PepperSpeechNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
