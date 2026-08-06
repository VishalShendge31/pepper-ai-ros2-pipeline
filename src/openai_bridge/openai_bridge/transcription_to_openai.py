#!/usr/bin/env python3

import re
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from openai_server_interfaces.srv import OpenaiServer


class TranscriptionToOpenaiNode(Node):
    def __init__(self):
        super().__init__("transcription_to_openai")

        self.declare_parameter("transcript_topic", "/whisper_transcript")
        self.declare_parameter("vlm_topic", "/smolvlm/output")
        self.declare_parameter("response_topic", "/openai_response")
        self.declare_parameter("service_name", "/openai_ask")

        self.declare_parameter("reset_conversation", True)
        self.declare_parameter("require_wake_word", True)
        self.declare_parameter("activation_timeout_sec", 8.0)
        self.declare_parameter("wake_words", ["hey pepper", "hello pepper", "pepper"])

        self.declare_parameter(
            "pre_prompt",
            (
                "You are Pepper, a helpful humanoid robot assistant. "
                "Answer concisely in German. "
                "Use the robot camera context naturally when it is available. "
                "Do not say that you received a visual description."
            ),
        )

        self.transcript_topic = self.get_parameter("transcript_topic").value
        self.vlm_topic = self.get_parameter("vlm_topic").value
        self.response_topic = self.get_parameter("response_topic").value
        self.service_name = self.get_parameter("service_name").value

        self.reset_conversation = bool(self.get_parameter("reset_conversation").value)
        self.require_wake_word = bool(self.get_parameter("require_wake_word").value)
        self.activation_timeout_sec = float(self.get_parameter("activation_timeout_sec").value)
        self.wake_words = list(self.get_parameter("wake_words").value)
        self.pre_prompt = self.get_parameter("pre_prompt").value

        self.latest_vlm = ""

        self.is_activated = False
        self.last_activation_time = 0.0

        self.sub_vlm = self.create_subscription(
            String,
            self.vlm_topic,
            self.vlm_callback,
            10,
        )

        self.sub_transcript = self.create_subscription(
            String,
            self.transcript_topic,
            self.transcript_callback,
            10,
        )

        self.pub_response = self.create_publisher(
            String,
            self.response_topic,
            10,
        )

        self.client = self.create_client(OpenaiServer, self.service_name)

        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info(f"Waiting for service {self.service_name}")

        self.get_logger().info(f"Listening to ASR: {self.transcript_topic}")
        self.get_logger().info(f"Listening to VLM: {self.vlm_topic}")
        self.get_logger().info(f"Publishing response: {self.response_topic}")
        self.get_logger().info(f"Wake-word mode: {self.require_wake_word}")
        self.get_logger().info(f"Wake words: {self.wake_words}")
        self.get_logger().info(f"Activation timeout: {self.activation_timeout_sec}s")

    def vlm_callback(self, msg: String):
        text = msg.data.strip()

        if text:
            self.latest_vlm = text
            self.get_logger().debug(f"Updated VLM context: {text}")

    def normalize_text(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def extract_command_after_wake_word(self, transcript: str):
        normalized = self.normalize_text(transcript)

        for wake_word in self.wake_words:
            wake = self.normalize_text(wake_word)

            if normalized == wake:
                return ""

            if normalized.startswith(wake + " "):
                return normalized[len(wake):].strip()

            padded_text = f" {normalized} "
            padded_wake = f" {wake} "

            if padded_wake in padded_text:
                parts = normalized.split(wake, 1)
                if len(parts) > 1:
                    return parts[1].strip()

        return None

    def activate(self):
        self.is_activated = True
        self.last_activation_time = time.time()
        self.get_logger().info("Wake word detected. Pepper is now listening.")

    def is_activation_valid(self) -> bool:
        if not self.is_activated:
            return False

        elapsed = time.time() - self.last_activation_time
        return elapsed <= self.activation_timeout_sec

    def build_prompt(self, user_question: str) -> str:
        if self.latest_vlm:
            return (
                f"[Robot Camera Context]\n"
                f"{self.latest_vlm}\n\n"
                f"[User Question]\n"
                f"{user_question}"
            )

        return user_question

    def transcript_callback(self, msg: String):
        raw_transcript = msg.data.strip()

        if not raw_transcript:
            return

        self.get_logger().info(f"Received transcript: {raw_transcript}")

        if self.require_wake_word:
            user_question = self.extract_command_after_wake_word(raw_transcript)

            if user_question is None:
                self.get_logger().info("Ignored transcript because wake word was not detected")
                return

            if not user_question:
                self.get_logger().info("Wake word only. Waiting for command.")
                return
        else:
            user_question = raw_transcript

        prompt = self.build_prompt(user_question)

        req = OpenaiServer.Request()
        req.prompt = prompt
        req.reset_conversation = self.reset_conversation
        req.pre_prompt = self.pre_prompt

        future = self.client.call_async(req)
        future.add_done_callback(self.response_callback)

        self.get_logger().info(f"Sent to OpenAI: {prompt}")

    def response_callback(self, future):
        try:
            response = future.result()
            text = response.response.strip()

            if not text:
                self.get_logger().warn("OpenAI returned empty response")
                return

            msg = String()
            msg.data = text
            self.pub_response.publish(msg)

            self.get_logger().info(f"Published OpenAI response: {text}")

        except Exception as e:
            self.get_logger().error(f"OpenAI service failed: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = TranscriptionToOpenaiNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
