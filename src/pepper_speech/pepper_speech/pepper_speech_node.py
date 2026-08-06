#!/usr/bin/env python3

import subprocess
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class PepperSpeechNode(Node):
    def __init__(self):
        super().__init__("pepper_speech_node")

        self.declare_parameter("input_topic", "/openai_response")
        self.declare_parameter("speech_topic", "/speech")

        self.declare_parameter("use_animated_speech", True)
        self.declare_parameter("robot_ip", "192.168.100.20")
        self.declare_parameter("robot_user", "nao")
        self.declare_parameter("body_language_mode", "contextual")
        self.declare_parameter("fallback_to_speech_topic", False)
        self.declare_parameter("set_german_language", True)

        self.input_topic = self.get_parameter("input_topic").value
        self.speech_topic = self.get_parameter("speech_topic").value

        self.use_animated_speech = bool(self.get_parameter("use_animated_speech").value)
        self.robot_ip = self.get_parameter("robot_ip").value
        self.robot_user = self.get_parameter("robot_user").value
        self.body_language_mode = self.get_parameter("body_language_mode").value
        self.fallback_to_speech_topic = bool(
            self.get_parameter("fallback_to_speech_topic").value
        )
        self.set_german_language = bool(
            self.get_parameter("set_german_language").value
        )

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

        self.speech_lock = threading.Lock()

        self.get_logger().info(f"Listening to LLM response: {self.input_topic}")
        self.get_logger().info(f"Fallback speech topic: {self.speech_topic}")
        self.get_logger().info(f"Animated speech enabled: {self.use_animated_speech}")
        self.get_logger().info(f"Pepper SSH target: {self.robot_user}@{self.robot_ip}")
        self.get_logger().info(f"Body language mode: {self.body_language_mode}")

    def response_callback(self, msg: String):
        text = msg.data.strip()

        if not text:
            self.get_logger().warn("Empty response received")
            return

        if self.use_animated_speech:
            thread = threading.Thread(
                target=self.say_with_animated_speech,
                args=(text,),
                daemon=True,
            )
            thread.start()
            return

        self.publish_to_speech_topic(text)

    def say_with_animated_speech(self, text: str):
        if not self.speech_lock.acquire(blocking=False):
            self.get_logger().warn("Pepper is already speaking. Ignoring overlapping response.")
            return

        try:
            python_code = f"""# -*- coding: utf-8 -*-
from naoqi import ALProxy

text = {text!r}
body_language_mode = {self.body_language_mode!r}
set_german_language = {self.set_german_language!r}

try:
    motion = ALProxy("ALMotion", "127.0.0.1", 9559)
    motion.wakeUp()
except Exception as e:
    print("wakeUp skipped:", e)

try:
    tts = ALProxy("ALTextToSpeech", "127.0.0.1", 9559)
    if set_german_language:
        try:
            tts.setLanguage("German")
        except Exception as e:
            print("setLanguage skipped:", e)
except Exception as e:
    print("TTS proxy skipped:", e)

animated = ALProxy("ALAnimatedSpeech", "127.0.0.1", 9559)

config = {{
    "bodyLanguageMode": body_language_mode
}}

animated.say(text, config)
"""

            remote_cmd = (
                "export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH; "
                "export LD_LIBRARY_PATH=/opt/aldebaran/lib:$LD_LIBRARY_PATH; "
                "python2 - <<'PY'\n"
                f"{python_code}\n"
                "PY"
            )

            cmd = [
                "ssh",
                "-o",
                "ConnectTimeout=5",
                f"{self.robot_user}@{self.robot_ip}",
                remote_cmd,
            ]

            self.get_logger().info(f"AnimatedSpeech contextual say: {text}")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=45.0,
            )

            if result.stdout.strip():
                self.get_logger().info(result.stdout.strip())

            if result.returncode != 0:
                self.get_logger().error(result.stderr.strip())

                if self.fallback_to_speech_topic:
                    self.publish_to_speech_topic(text)

        except Exception as exc:
            self.get_logger().error(f"Animated speech failed: {exc}")

            if self.fallback_to_speech_topic:
                self.publish_to_speech_topic(text)

        finally:
            self.speech_lock.release()

    def publish_to_speech_topic(self, text: str):
        out = String()
        out.data = text
        self.pub.publish(out)

        self.get_logger().info(f"Sent to Pepper speech topic: {text}")


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
