#!/usr/bin/env python3

import re
import time
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from naoqi_bridge_msgs.msg import AudioBuffer

from faster_whisper import WhisperModel
from silero_vad import load_silero_vad, VADIterator

try:
    import librosa
    HAS_LIBROSA = True
except Exception:
    HAS_LIBROSA = False


class StreamingFasterWhisperVAD(Node):
    def __init__(self):
        super().__init__("streaming_faster_whisper_vad")

        self.declare_parameter("audio_topic", "/audio")
        self.declare_parameter("output_topic", "/whisper_transcript")

        self.declare_parameter("model_size", "small")
        self.declare_parameter("device", "cuda")
        self.declare_parameter("compute_type", "float16")
        self.declare_parameter("language", "en")

        self.declare_parameter("target_sample_rate", 16000)
        self.declare_parameter("min_segment_sec", 0.6)
        self.declare_parameter("max_segment_sec", 15.0)
        self.declare_parameter("min_rms", 0.005)

        self.declare_parameter("vad_threshold", 0.35)
        self.declare_parameter("min_silence_duration_ms", 1000)
        self.declare_parameter("speech_pad_ms", 700)

        self.declare_parameter("require_wake_word", True)
        self.declare_parameter("activation_timeout_sec", 8.0)
        self.declare_parameter(
            "wake_words",
            [
                "hey pepper",
                "hello pepper",
                "pepper",
                "hey peppa",
                "hello peppa",
                "peppa",
                "hey paper",
                "hello paper",
                "paper",
                "okay pepper",
                "ok pepper",
                "hi pepper",
            ],
        )

        self.audio_topic = self.get_parameter("audio_topic").value
        self.output_topic = self.get_parameter("output_topic").value

        self.model_size = self.get_parameter("model_size").value
        self.device = self.get_parameter("device").value
        self.compute_type = self.get_parameter("compute_type").value

        lang = self.get_parameter("language").value
        self.language = None if lang == "auto" else lang

        self.target_sample_rate = int(self.get_parameter("target_sample_rate").value)
        self.min_segment_sec = float(self.get_parameter("min_segment_sec").value)
        self.max_segment_sec = float(self.get_parameter("max_segment_sec").value)
        self.min_rms = float(self.get_parameter("min_rms").value)

        self.vad_threshold = float(self.get_parameter("vad_threshold").value)
        self.min_silence_duration_ms = int(self.get_parameter("min_silence_duration_ms").value)
        self.speech_pad_ms = int(self.get_parameter("speech_pad_ms").value)

        self.require_wake_word = bool(self.get_parameter("require_wake_word").value)
        self.activation_timeout_sec = float(self.get_parameter("activation_timeout_sec").value)
        self.wake_words = list(self.get_parameter("wake_words").value)

        self.is_activated = False
        self.last_activation_time = 0.0

        try:
            self.get_logger().info(
                f"Loading faster-whisper model={self.model_size}, device={self.device}, compute_type={self.compute_type}"
            )
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as e:
            self.get_logger().warn(f"CUDA/runtime failed, using CPU int8: {e}")
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )

        self.vad_model = load_silero_vad()
        self.vad = VADIterator(
            self.vad_model,
            threshold=self.vad_threshold,
            sampling_rate=self.target_sample_rate,
            min_silence_duration_ms=self.min_silence_duration_ms,
            speech_pad_ms=self.speech_pad_ms,
        )

        self.pub = self.create_publisher(String, self.output_topic, 10)

        self.sub = self.create_subscription(
            AudioBuffer,
            self.audio_topic,
            self.audio_callback,
            50,
        )

        self.vad_frame_size = 512
        self.vad_buffer = np.empty((0,), dtype=np.float32)

        self.segment_active = False
        self.segment_samples = []

        self.preroll_frames = []
        self.preroll_max_frames = 30

        self.get_logger().info(f"ASR listening on {self.audio_topic}")
        self.get_logger().info(f"ASR publishing commands on {self.output_topic}")
        self.get_logger().info(f"Wake-word mode: {self.require_wake_word}")
        self.get_logger().info(f"Wake words: {self.wake_words}")
        self.get_logger().info(f"Activation timeout: {self.activation_timeout_sec}s")

    def audio_callback(self, msg):
        try:
            raw = np.asarray(msg.data, dtype=np.int16)

            if raw.size == 0:
                return

            channels = max(1, len(msg.channel_map))
            src_sr = int(msg.frequency)

            mono = self.to_mono(raw, channels)
            audio_16k = self.resample(mono, src_sr, self.target_sample_rate)
            audio_float = audio_16k.astype(np.float32) / 32768.0

            self.process_chunk(audio_float)

        except Exception as e:
            self.get_logger().error(f"Audio callback failed: {e}")

    def to_mono(self, raw, channels):
        if channels <= 1:
            return raw.reshape(-1)

        usable = (raw.size // channels) * channels
        data = raw[:usable].reshape(-1, channels)
        mono = data.astype(np.float32).mean(axis=1)

        return mono.clip(-32768, 32767).astype(np.int16)

    def resample(self, audio, src_sr, target_sr):
        if src_sr == target_sr:
            return audio

        if not HAS_LIBROSA:
            raise RuntimeError("librosa is required for resampling because /audio is not 16 kHz")

        audio_float = audio.astype(np.float32) / 32768.0
        y = librosa.resample(audio_float, orig_sr=src_sr, target_sr=target_sr)

        return (y * 32768.0).clip(-32768, 32767).astype(np.int16)

    def process_chunk(self, chunk):
        self.vad_buffer = np.concatenate([self.vad_buffer, chunk])

        while self.vad_buffer.size >= self.vad_frame_size:
            frame = self.vad_buffer[:self.vad_frame_size]
            self.vad_buffer = self.vad_buffer[self.vad_frame_size:]

            self.preroll_frames.append(frame.copy())
            if len(self.preroll_frames) > self.preroll_max_frames:
                self.preroll_frames.pop(0)

            event = self.vad(frame)

            if self.segment_active:
                self.segment_samples.append(frame.copy())

            if event:
                if "start" in event:
                    self.segment_active = True
                    self.segment_samples = list(self.preroll_frames) + [frame.copy()]

                if "end" in event and self.segment_active:
                    segment = np.concatenate(self.segment_samples)
                    self.segment_active = False
                    self.segment_samples = []
                    self.transcribe(segment)

            if self.segment_active:
                duration = sum(len(x) for x in self.segment_samples) / self.target_sample_rate

                if duration >= self.max_segment_sec:
                    segment = np.concatenate(self.segment_samples)
                    self.segment_active = False
                    self.segment_samples = []
                    self.transcribe(segment)

    def normalize_text(self, text):
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def extract_command_after_wake_word(self, text):
        normalized = self.normalize_text(text)

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

    def is_activation_valid(self):
        if not self.is_activated:
            return False

        elapsed = time.time() - self.last_activation_time
        return elapsed <= self.activation_timeout_sec

    def publish_command(self, text):
        text = text.strip()

        if not text:
            return

        msg = String()
        msg.data = text
        self.pub.publish(msg)

        self.get_logger().info(f"Published command: {text}")

    def handle_transcript(self, text):
        self.get_logger().info(f"Raw transcript: {text}")

        if not self.require_wake_word:
            self.publish_command(text)
            return

        command = self.extract_command_after_wake_word(text)

        if command is not None:
            self.activate()

            if command:
                self.publish_command(command)
                self.is_activated = False
            else:
                self.get_logger().info("Wake word only. Waiting for next command.")
            return

        if self.is_activation_valid():
            self.publish_command(text)
            self.is_activated = False
            return

        self.get_logger().info("Ignored transcript because wake word was not detected")

    def transcribe(self, audio):
        duration = len(audio) / self.target_sample_rate

        if duration < self.min_segment_sec:
            return

        rms = float(np.sqrt(np.mean(audio ** 2)))

        if rms < self.min_rms:
            return

        try:
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                condition_on_previous_text=False,
                initial_prompt=(
                    "The user may say wake phrases such as Hey Pepper, Hello Pepper, "
                    "Pepper, Hey Peppa, or Hey Paper before asking a question."
                ),
            )

            if info.language not in ["en", "de"]:
                self.get_logger().warn(f"Ignored unsupported language: {info.language}")
                return

            text = " ".join(
                seg.text.strip()
                for seg in segments
                if seg.text and seg.text.strip()
            ).strip()

            if not text:
                return

            self.handle_transcript(text)

        except Exception as e:
            self.get_logger().error(f"Transcription failed: {e}")

    def destroy_node(self):
        try:
            self.vad.reset_states()
        except Exception:
            pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = StreamingFasterWhisperVAD()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
