import rclpy
from rclpy.node import Node


class PepperSystemMonitor(Node):
    def __init__(self):
        super().__init__("pepper_system_monitor")

        self.declare_parameter("nao_ip", "192.168.100.20")
        self.declare_parameter("host_ip", "192.168.100.172")
        self.declare_parameter("dashboard_port", "5000")

        self.required_topics = [
            "/audio",
            "/camera/front/image_raw",
            "/whisper_transcript",
            "/openai_response",
            "/smolvlm/output",
            "/cmd_vel",
            "/speech",
        ]

        self.timer = self.create_timer(5.0, self.check_topics)

        self.get_logger().info("Pepper system monitor started.")

    def check_topics(self):
        topic_names_and_types = self.get_topic_names_and_types()
        active_topics = [name for name, _ in topic_names_and_types]

        missing_topics = [
            topic for topic in self.required_topics
            if topic not in active_topics
        ]

        if missing_topics:
            self.get_logger().warn(
                "Missing topics: " + ", ".join(missing_topics)
            )
        else:
            self.get_logger().info(
                "All required Pepper AI pipeline topics are active."
            )


def main(args=None):
    rclpy.init(args=args)
    node = PepperSystemMonitor()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()