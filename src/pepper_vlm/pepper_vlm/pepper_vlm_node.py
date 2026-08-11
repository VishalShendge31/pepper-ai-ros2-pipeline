#!/usr/bin/env python3

import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

import re
import time

import rclpy
import torch
from cv_bridge import CvBridge
from PIL import Image as PILImage
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from transformers import AutoModelForImageTextToText, AutoProcessor


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class SmolVLMNode(Node):
    """Scene VLM node for Pepper with structured social-skill output.

    SmolVLM generates an open German scene sentence. Lightweight keyword
    heuristics then fill PERSON / GESTURE / EMOTION so /smolvlm/output matches
    what social_skill_manager.parse_vlm_context() expects. Gender and emotion
    stay conservative (unknown) unless clear face-API fields are wired later.
    """

    def __init__(self):
        super().__init__("smolvlm_node")

        self.declare_parameter("camera_topic", "/camera/front/image_raw")
        self.declare_parameter("output_topic", "/smolvlm/output")
        self.declare_parameter("process_interval_sec", 1.5)
        self.declare_parameter("model_name", "HuggingFaceTB/SmolVLM-500M-Instruct")
        self.declare_parameter("max_new_tokens", 80)
        self.declare_parameter("max_scene_chars", 260)
        self.declare_parameter("emit_structured_fields", True)

        self.camera_topic = self.get_parameter("camera_topic").value
        self.output_topic = self.get_parameter("output_topic").value
        self.process_interval_sec = float(self.get_parameter("process_interval_sec").value)
        self.model_name = self.get_parameter("model_name").value
        self.max_new_tokens = int(self.get_parameter("max_new_tokens").value)
        self.max_scene_chars = int(self.get_parameter("max_scene_chars").value)
        self.emit_structured_fields = bool(
            self.get_parameter("emit_structured_fields").value
        )

        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            size={"longest_edge": 768},
        )

        self.model = AutoModelForImageTextToText.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if DEVICE == "cuda" else torch.float32,
        ).to(DEVICE)
        self.model.eval()

        self.bridge = CvBridge()
        self.is_processing = False
        self.last_process_time = 0.0

        qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
        )

        self.sub = self.create_subscription(
            Image,
            self.camera_topic,
            self.image_callback,
            qos,
        )
        self.pub = self.create_publisher(String, self.output_topic, 10)

        self.get_logger().info(f"VLM camera input: {self.camera_topic}")
        self.get_logger().info(f"VLM output: {self.output_topic}")
        self.get_logger().info(f"VLM model: {self.model_name}")
        self.get_logger().info(
            "VLM mode: German scene description + structured PERSON/GESTURE/EMOTION/SCENE."
        )

    def build_scene_prompt(self):
        return (
            "Beschreibe nur das aktuelle Kamerabild in genau einem natürlichen deutschen Satz. "
            "Beginne mit 'Ich sehe'. "
            "Nenne konkrete sichtbare Details wie Personen, Körperhaltung, Objekte, Raum oder Hintergrund. "
            "Erfinde keine Identität, kein Alter, kein Geschlecht und keine Emotion. "
            "Bewerte keine Stimmung und keine soziale Absicht. "
            "Schreibe nicht 'in diesem Bild', nicht 'das Bild zeigt' und keine Erklärung."
        )

    def image_callback(self, msg: Image):
        now = time.time()

        if self.is_processing:
            return

        if now - self.last_process_time < self.process_interval_sec:
            return

        self.is_processing = True
        self.last_process_time = now

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            pil_image = PILImage.fromarray(cv_image[:, :, ::-1])

            raw = self.generate_from_image(
                pil_image=pil_image,
                prompt_text=self.build_scene_prompt(),
                max_new_tokens=self.max_new_tokens,
            )

            scene = self.clean_scene_sentence(raw)
            if self.is_bad_scene(scene):
                scene = "Ich sehe im Moment keine zuverlässigen Details."

            scene = scene[: self.max_scene_chars].strip()
            out = String()
            out.data = self.format_output(scene)
            self.pub.publish(out)
            self.get_logger().info(f"VLM scene: {out.data}")

        except Exception as exc:
            self.get_logger().error(f"VLM processing failed: {exc}")
        finally:
            self.is_processing = False

    def generate_from_image(self, pil_image, prompt_text, max_new_tokens):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]

        prompt = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
        )

        inputs = self.processor(
            text=prompt,
            images=[pil_image],
            return_tensors="pt",
        ).to(DEVICE)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=1,
            )

        input_len = inputs["input_ids"].shape[-1]
        new_tokens = generated_ids[:, input_len:]
        if new_tokens.numel() == 0:
            new_tokens = generated_ids

        text = self.processor.batch_decode(
            new_tokens,
            skip_special_tokens=True,
        )[0]
        return text.strip()

    def normalize(self, text: str) -> str:
        text = (text or "").lower().strip()
        text = re.sub(r"[^\w\säöüß]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def infer_social_fields(self, scene: str):
        """Derive conservative PERSON/GESTURE/EMOTION labels from the scene sentence."""
        normalized = self.normalize(scene)

        person_keywords = [
            "mann",
            "frau",
            "mensch",
            "person",
            "personen",
            "gesicht",
            "gesichter",
            "jemand",
            "leute",
            "kind",
            "besucher",
            "man",
            "woman",
            "people",
            "person",
            "face",
            "human",
        ]
        person = "unknown" if any(k in normalized for k in person_keywords) else "none"

        wave_keywords = [
            "winkt",
            "winken",
            "waving",
            "wave",
            "hand gehoben",
            "gehobene hand",
            "hand hoch",
            "raised hand",
            "hand raised",
        ]
        point_keywords = ["zeigt", "pointing", "zeigt auf", "deutet"]
        look_keywords = [
            "schaut den roboter",
            "schaut mich",
            "blick zum roboter",
            "looking at",
            "schaut auf pepper",
        ]

        if any(k in normalized for k in wave_keywords):
            gesture = "waving"
        elif any(k in normalized for k in point_keywords):
            gesture = "pointing"
        elif any(k in normalized for k in look_keywords):
            gesture = "looking_at_robot"
        elif person != "none":
            gesture = "unknown"
        else:
            gesture = "none"

        # Do not invent emotion from a scene caption; leave unknown for face-API later.
        emotion = "unknown"

        return person, gesture, emotion

    def format_output(self, scene: str) -> str:
        if not self.emit_structured_fields:
            return f"SCENE: {scene}"

        person, gesture, emotion = self.infer_social_fields(scene)
        return (
            f"PERSON: {person}\n"
            f"GESTURE: {gesture}\n"
            f"EMOTION: {emotion}\n"
            f"SCENE: {scene}"
        )

    def clean_scene_sentence(self, text: str) -> str:
        text = (text or "").strip()
        text = text.replace("```", "")
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\s+", " ", text).strip()

        prefixes = [
            "SCENE:",
            "Szene:",
            "Scene:",
            "Antwort:",
            "Deutsch:",
            "German:",
            "Beschreibung:",
            "Bildbeschreibung:",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        replacements = [
            (r"(?i)^in diesem bild sehe ich\s+", "Ich sehe "),
            (r"(?i)^auf diesem bild sehe ich\s+", "Ich sehe "),
            (r"(?i)^im bild sehe ich\s+", "Ich sehe "),
            (r"(?i)^das bild zeigt\s+", "Ich sehe "),
            (r"(?i)^the image shows\s+", "Ich sehe "),
            (r"(?i)^in this image[, ]*\s*", ""),
            (r"(?i)^in the image[, ]*\s*", ""),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text).strip()

        text = re.sub(r"(?i)\bin diesem bild\b", "", text).strip()
        text = re.sub(r"(?i)\bauf diesem bild\b", "", text).strip()
        text = re.sub(r"(?i)\bim bild\b", "", text).strip()
        text = re.sub(r"\s+", " ", text).strip()

        # Keep the first complete sentence. This reduces hallucinated follow-up text.
        parts = re.split(r"(?<=[.!?])\s+", text)
        if parts:
            text = parts[0].strip()

        if text and not text.endswith((".", "!", "?")):
            text += "."

        return text

    def is_bad_scene(self, scene: str) -> bool:
        if not scene:
            return True

        lower = scene.lower().strip()
        bad_fragments = [
            "describe scene",
            "beschreibe nur",
            "schreibe nicht",
            "genau einem natürlichen deutschen satz",
            "one natural german sentence",
            "instruction",
            "format",
            "sichtbare szene",
            "visible scene",
            "unknown",
            "none",
        ]
        if any(fragment in lower for fragment in bad_fragments):
            return True

        too_generic_exact = [
            "ich sehe eine szene.",
            "ich sehe eine person.",
            "eine person ist zu sehen.",
            "es ist eine person zu sehen.",
        ]
        if lower in too_generic_exact:
            return True

        return len(lower) < 12


def main(args=None):
    rclpy.init(args=args)
    node = SmolVLMNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
