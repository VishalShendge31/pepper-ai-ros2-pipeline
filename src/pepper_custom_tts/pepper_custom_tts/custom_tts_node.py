#!/usr/bin/env python3
"""
ROS 2 node that replaces Pepper's built-in TTS path.

Input:
    /openai_response     std_msgs/String

Output:
    /pepper_tts/status   std_msgs/String
    /pepper_tts/audio_file std_msgs/String

Runtime behavior:
    1. Receives text from the LLM bridge.
    2. Sends the text to a local Spark-TTS HTTP server.
    3. Receives a generated WAV path.
    4. Plays locally, copies to Pepper through scp, or both.

No Python script is required inside Pepper. Pepper only receives scp and qicli SSH calls.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


@dataclass
class TTSJob:
    text: str
    created_at: float


class PepperCustomTTS(Node):
    def __init__(self) -> None:
        super().__init__("pepper_custom_tts")

        self.declare_parameter("input_topic", "/openai_response")
        self.declare_parameter("status_topic", "/pepper_tts/status")
        self.declare_parameter("audio_path_topic", "/pepper_tts/audio_file")

        self.declare_parameter("tts_server_url", "http://127.0.0.1:8765/tts")
        self.declare_parameter("request_timeout_sec", 180.0)

        self.declare_parameter("default_emotion", "neutral")
        self.declare_parameter("max_text_chars", 350)
        self.declare_parameter("drop_when_busy", True)

        self.declare_parameter("playback_mode", "pepper_ssh")
        self.declare_parameter("local_player_cmd", "aplay")

        self.declare_parameter("robot_ip", "192.168.100.20")
        self.declare_parameter("robot_user", "nao")
        self.declare_parameter("ssh_port", 22)
        self.declare_parameter("remote_audio_dir", "/home/nao")
        self.declare_parameter("remote_audio_filename", "custom_tts_output.wav")
        self.declare_parameter("unique_remote_filename", False)

        self.declare_parameter("wake_before_speak", False)
        self.declare_parameter("ssh_connect_timeout_sec", 10)
        self.declare_parameter("scp_timeout_sec", 60)
        self.declare_parameter("pepper_play_timeout_sec", 120)
        self.declare_parameter("delete_local_after_playback", False)

        self.input_topic = self.get_parameter("input_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.audio_path_topic = self.get_parameter("audio_path_topic").value

        self.tts_server_url = self.get_parameter("tts_server_url").value
        self.request_timeout_sec = float(self.get_parameter("request_timeout_sec").value)

        self.default_emotion = self.get_parameter("default_emotion").value
        self.max_text_chars = int(self.get_parameter("max_text_chars").value)
        self.drop_when_busy = bool(self.get_parameter("drop_when_busy").value)

        self.playback_mode = self.get_parameter("playback_mode").value
        self.local_player_cmd = self.get_parameter("local_player_cmd").value

        self.robot_ip = self.get_parameter("robot_ip").value
        self.robot_user = self.get_parameter("robot_user").value
        self.ssh_port = int(self.get_parameter("ssh_port").value)
        self.remote_audio_dir = self.get_parameter("remote_audio_dir").value.rstrip("/")
        self.remote_audio_filename = self.get_parameter("remote_audio_filename").value
        self.unique_remote_filename = bool(self.get_parameter("unique_remote_filename").value)

        self.wake_before_speak = bool(self.get_parameter("wake_before_speak").value)
        self.ssh_connect_timeout_sec = int(self.get_parameter("ssh_connect_timeout_sec").value)
        self.scp_timeout_sec = int(self.get_parameter("scp_timeout_sec").value)
        self.pepper_play_timeout_sec = int(self.get_parameter("pepper_play_timeout_sec").value)
        self.delete_local_after_playback = bool(self.get_parameter("delete_local_after_playback").value)

        self.status_pub = self.create_publisher(String, self.status_topic, 10)
        self.audio_path_pub = self.create_publisher(String, self.audio_path_topic, 10)

        self.job_queue: queue.Queue[TTSJob] = queue.Queue(maxsize=1)
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

        self.sub = self.create_subscription(String, self.input_topic, self._on_text, 10)

        self._publish_status("ready")
        self.get_logger().info("Pepper Custom TTS node started")
        self.get_logger().info(f"Input topic: {self.input_topic}")
        self.get_logger().info(f"TTS server: {self.tts_server_url}")
        self.get_logger().info(f"Playback mode: {self.playback_mode}")

    def _on_text(self, msg: String) -> None:
        text = self._normalize_text(msg.data)
        if not text:
            self.get_logger().warn("Received empty text. Skipping TTS.")
            return

        job = TTSJob(text=text, created_at=time.time())

        if self.drop_when_busy and self.job_queue.full():
            self.get_logger().warn("TTS queue is full. Dropping new response because drop_when_busy=true.")
            self._publish_status("busy_drop")
            return

        try:
            self.job_queue.put_nowait(job)
            self._publish_status("queued")
        except queue.Full:
            self.get_logger().warn("TTS queue is full. Response skipped.")
            self._publish_status("busy_drop")

    def _worker_loop(self) -> None:
        while True:
            job = self.job_queue.get()
            try:
                self._publish_status("generating")
                wav_path = self._request_tts(job.text)
                self._publish_audio_path(wav_path)

                self._publish_status("playing")
                self._play_audio(wav_path)

                self._publish_status("done")

                if self.delete_local_after_playback:
                    self._safe_delete(wav_path)

            except Exception as exc:
                self.get_logger().error(f"Custom TTS failed: {exc}")
                self._publish_status(f"error: {exc}")
            finally:
                self.job_queue.task_done()

    def _normalize_text(self, text: str) -> str:
        text = (text or "").strip()
        text = text.replace("\u0000", "")
        text = " ".join(text.split())

        if len(text) > self.max_text_chars:
            text = text[: self.max_text_chars].rsplit(" ", 1)[0].strip()

        return text

    def _request_tts(self, text: str) -> str:
        payload = {
            "text": text,
            "emotion": self.default_emotion,
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.tts_server_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_sec) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                error_body = str(exc)
            raise RuntimeError(f"Spark-TTS server returned HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not contact Spark-TTS server at {self.tts_server_url}: {exc}") from exc

        result = json.loads(response_body)
        if not result.get("ok", False):
            raise RuntimeError(result.get("error", "Spark-TTS server returned an unknown error"))

        wav_path = result.get("wav_path")
        if not wav_path:
            raise RuntimeError("Spark-TTS server did not return wav_path")

        if not Path(wav_path).exists():
            raise RuntimeError(f"Spark-TTS returned a missing WAV path: {wav_path}")

        return wav_path

    def _play_audio(self, wav_path: str) -> None:
        mode = self.playback_mode.strip().lower()

        if mode == "none":
            return

        if mode in ("local", "both"):
            self._play_local(wav_path)

        if mode in ("pepper_ssh", "pepper", "both"):
            remote_path = self._copy_to_pepper(wav_path)
            self._play_on_pepper(remote_path)

        if mode not in ("none", "local", "both", "pepper_ssh", "pepper"):
            raise RuntimeError(f"Unsupported playback_mode: {self.playback_mode}")

    def _play_local(self, wav_path: str) -> None:
        cmd = shlex.split(self.local_player_cmd) + [wav_path]
        self.get_logger().info("Playing generated audio locally")
        subprocess.run(cmd, check=True)

    def _copy_to_pepper(self, wav_path: str) -> str:
        if self.unique_remote_filename:
            stem = Path(self.remote_audio_filename).stem
            suffix = Path(self.remote_audio_filename).suffix or ".wav"
            remote_name = f"{stem}_{int(time.time() * 1000)}{suffix}"
        else:
            remote_name = self.remote_audio_filename

        remote_path = f"{self.remote_audio_dir}/{remote_name}"
        remote_target = f"{self.robot_user}@{self.robot_ip}:{remote_path}"

        scp_cmd = [
            "scp",
            "-P",
            str(self.ssh_port),
            "-o",
            f"ConnectTimeout={self.ssh_connect_timeout_sec}",
            wav_path,
            remote_target,
        ]

        self.get_logger().info(f"Copying WAV to Pepper: {remote_path}")
        subprocess.run(scp_cmd, check=True, timeout=self.scp_timeout_sec)
        return remote_path

    def _play_on_pepper(self, remote_path: str) -> None:
        ssh_base = [
            "ssh",
            "-p",
            str(self.ssh_port),
            "-o",
            f"ConnectTimeout={self.ssh_connect_timeout_sec}",
            f"{self.robot_user}@{self.robot_ip}",
        ]

        if self.wake_before_speak:
            self.get_logger().info("Calling ALMotion.wakeUp before speech")
            subprocess.run(
                ssh_base + ["qicli call ALMotion.wakeUp"],
                check=True,
                timeout=self.pepper_play_timeout_sec,
            )

        self.get_logger().info("Playing generated audio through Pepper speaker")
        play_cmd = f"qicli call ALAudioPlayer.playFile {shlex.quote(remote_path)}"
        subprocess.run(
            ssh_base + [play_cmd],
            check=True,
            timeout=self.pepper_play_timeout_sec,
        )

    def _publish_status(self, status: str) -> None:
        msg = String()
        msg.data = status
        self.status_pub.publish(msg)

    def _publish_audio_path(self, wav_path: str) -> None:
        msg = String()
        msg.data = wav_path
        self.audio_path_pub.publish(msg)

    def _safe_delete(self, path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = PepperCustomTTS()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
