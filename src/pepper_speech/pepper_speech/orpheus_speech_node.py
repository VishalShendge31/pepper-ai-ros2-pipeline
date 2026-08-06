#!/usr/bin/env python3

import os
import re
import socket
import struct
import tempfile

import numpy as np
import rclpy
import soundfile as sf
import torch

from rclpy.node import Node
from std_msgs.msg import String
from snac import SNAC
from unsloth import FastLanguageModel


TOKENISER_LENGTH = 128256
START_OF_TEXT = 128000
END_OF_TEXT = 128009
START_OF_SPEECH = TOKENISER_LENGTH + 1
END_OF_SPEECH = TOKENISER_LENGTH + 2
START_OF_HUMAN = TOKENISER_LENGTH + 3
END_OF_HUMAN = TOKENISER_LENGTH + 4
START_OF_AI = TOKENISER_LENGTH + 5
END_OF_AI = TOKENISER_LENGTH + 6
AUDIO_TOKENS_START = TOKENISER_LENGTH + 10


class OrpheusSpeechNode(Node):
    def __init__(self):
        super().__init__("orpheus_speech_node")

        self.declare_parameter("input_topic", "/openai_response")
        self.declare_parameter(
            "model_path",
            "/home/robot/pepper_ws/models/orpheus/orpheus-3b-tts-german-emotional-merged",
        )
        self.declare_parameter("pepper_ip", "192.168.100.20")
        self.declare_parameter("pepper_tts_port", 5005)

        self.declare_parameter("emotion", "Happy")
        self.declare_parameter("emotion_tag", "[happy]")
        self.declare_parameter("paralinguistic_tag", "[chuckles]")

        self.declare_parameter("max_seq_length", 2048)
        self.declare_parameter("max_new_tokens", 512)
        self.declare_parameter("temperature", 0.4)
        self.declare_parameter("top_p", 0.90)
        self.declare_parameter("repetition_penalty", 1.3)

        self.input_topic = self.get_parameter("input_topic").value
        self.model_path = self.get_parameter("model_path").value
        self.pepper_ip = self.get_parameter("pepper_ip").value
        self.pepper_tts_port = int(self.get_parameter("pepper_tts_port").value)

        self.emotion = self.get_parameter("emotion").value
        self.emotion_tag = self.get_parameter("emotion_tag").value
        self.paralinguistic_tag = self.get_parameter("paralinguistic_tag").value

        self.max_seq_length = int(self.get_parameter("max_seq_length").value)
        self.max_new_tokens = int(self.get_parameter("max_new_tokens").value)
        self.temperature = float(self.get_parameter("temperature").value)
        self.top_p = float(self.get_parameter("top_p").value)
        self.repetition_penalty = float(self.get_parameter("repetition_penalty").value)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.get_logger().info(f"Loading Orpheus model: {self.model_path}")
        self.get_logger().info(f"Device: {self.device}")

        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.model_path,
            max_seq_length=self.max_seq_length,
            dtype=None,
            load_in_4bit=True,
            local_files_only=True,
        )

        FastLanguageModel.for_inference(self.model)

        self.get_logger().info("Loading SNAC 24 kHz decoder")
        self.snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").to(self.device).eval()

        self.sub = self.create_subscription(
            String,
            self.input_topic,
            self.response_callback,
            10,
        )

        self.get_logger().info(f"Listening to: {self.input_topic}")
        self.get_logger().info(f"Sending WAV audio to Pepper: {self.pepper_ip}:{self.pepper_tts_port}")

    def normalize_german_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-zäöüß\s\d.,!?\-<>\[\]:]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def build_orpheus_prompt(self, text: str) -> str:
        text = text.strip()

        if not text.startswith("["):
            text = f"{self.emotion_tag}{self.paralinguistic_tag} {text}"

        return f"{self.emotion}: {text}"

    def remove_duplicate_frames(self, codes_list):
        if len(codes_list) % 7 != 0:
            return codes_list

        result = codes_list[:7]

        for i in range(7, len(codes_list), 7):
            if codes_list[i] != result[-7]:
                result.extend(codes_list[i:i + 7])

        return result

    def redistribute_codes(self, code_list):
        layer_1 = []
        layer_2 = []
        layer_3 = []

        for i in range(len(code_list) // 7):
            layer_1.append(code_list[7 * i] % 4096)

            layer_2.append(code_list[7 * i + 1] % 4096)

            layer_3.append(code_list[7 * i + 2] % 4096)
            layer_3.append(code_list[7 * i + 3] % 4096)

            layer_2.append(code_list[7 * i + 4] % 4096)

            layer_3.append(code_list[7 * i + 5] % 4096)
            layer_3.append(code_list[7 * i + 6] % 4096)

        codes = [
            torch.tensor(layer_1, dtype=torch.long).to(self.device).unsqueeze(0),
            torch.tensor(layer_2, dtype=torch.long).to(self.device).unsqueeze(0),
            torch.tensor(layer_3, dtype=torch.long).to(self.device).unsqueeze(0),
        ]

        return self.snac_model.decode(codes)

    def generate_audio(self, text: str):
        prompt = self.build_orpheus_prompt(text)
        normalized_prompt = self.normalize_german_text(prompt)

        self.get_logger().info(f"Orpheus prompt: {normalized_prompt}")

        tokens = self.tokenizer(
            normalized_prompt,
            add_special_tokens=True,
        ).input_ids

        input_ids = (
            [START_OF_HUMAN]
            + tokens
            + [END_OF_TEXT]
            + [END_OF_HUMAN]
            + [START_OF_AI]
            + [START_OF_SPEECH]
        )

        input_ids = torch.tensor([input_ids], dtype=torch.int64).to(self.device)

        self.get_logger().info("Starting Orpheus generation...")

        with torch.inference_mode():
            output = self.model.generate(
                input_ids=input_ids,
                max_new_tokens=self.max_new_tokens,
                do_sample=True,
                temperature=self.temperature,
                top_p=self.top_p,
                repetition_penalty=self.repetition_penalty,
                eos_token_id=END_OF_SPEECH,
                use_cache=True,
            )

        self.get_logger().info("Model generation finished. Extracting SNAC codes...")

        generated_tokens = output[0][input_ids.shape[1]:]

        gen_codes = []

        for token in generated_tokens:
            val = int(token.item())

            if val == END_OF_SPEECH:
                break

            if val >= AUDIO_TOKENS_START:
                gen_codes.append(val - AUDIO_TOKENS_START)

        usable_length = (len(gen_codes) // 7) * 7
        gen_codes = gen_codes[:usable_length]

        self.get_logger().info(f"Extracted SNAC codes: {len(gen_codes)}")

        if not gen_codes:
            raise RuntimeError("No SNAC audio codes generated by Orpheus model")

        clean_codes = self.remove_duplicate_frames(gen_codes)

        self.get_logger().info(f"SNAC codes after duplicate-frame cleanup: {len(clean_codes)}")

        if len(clean_codes) < 7:
            raise RuntimeError("Too few SNAC codes after cleanup")

        self.get_logger().info("Decoding SNAC audio...")

        audio_hat = self.redistribute_codes(clean_codes)
        audio = audio_hat.cpu().detach().numpy()[0, 0]

        audio = np.clip(audio, -1.0, 1.0).astype(np.float32)

        self.get_logger().info(f"Audio generated. Samples: {len(audio)}")

        return audio

    def audio_to_wav_bytes(self, audio, sample_rate=24000):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            sf.write(wav_path, audio, sample_rate, subtype="PCM_16")

            with open(wav_path, "rb") as f:
                wav_bytes = f.read()

            return wav_bytes

        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass

    def send_wav_to_pepper(self, wav_bytes: bytes):
        try:
            self.get_logger().info(f"Connecting to Pepper TCP audio server {self.pepper_ip}:{self.pepper_tts_port}")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30.0)
                sock.connect((self.pepper_ip, self.pepper_tts_port))

                size = len(wav_bytes)

                self.get_logger().info(f"Sending WAV size header: {size} bytes")
                sock.sendall(struct.pack(">Q", size))

                self.get_logger().info("Sending WAV payload...")
                sock.sendall(wav_bytes)

            self.get_logger().info("TCP send finished")
            return True

        except Exception as e:
            self.get_logger().error(f"Failed to send WAV to Pepper: {e}")
            return False

    def response_callback(self, msg: String):
        text = msg.data.strip()

        if not text:
            self.get_logger().warn("Empty text received")
            return

        self.get_logger().info(f"Generating Orpheus speech for: {text}")

        try:
            audio = self.generate_audio(text)
            wav_bytes = self.audio_to_wav_bytes(audio, sample_rate=24000)

            self.get_logger().info(f"Generated WAV size: {len(wav_bytes)} bytes")

            if self.send_wav_to_pepper(wav_bytes):
                self.get_logger().info("Sent Orpheus audio to Pepper")
            else:
                self.get_logger().error("Could not send Orpheus audio to Pepper")

        except Exception as e:
            self.get_logger().error(f"Orpheus generation failed: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = OrpheusSpeechNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
