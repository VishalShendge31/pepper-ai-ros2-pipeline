#!/usr/bin/env python3

import json
import re
import time
from enum import Enum

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist

from openai_server_interfaces.srv import OpenaiServer


class SocialState(str, Enum):
    IDLE = "IDLE"
    PERSON_DETECTED = "PERSON_DETECTED"
    GREETING = "GREETING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    FOLLOW_UP = "FOLLOW_UP"
    GOODBYE = "GOODBYE"
    STOPPED = "STOPPED"


class SocialSkillManager(Node):
    def __init__(self):
        super().__init__("social_skill_manager")

        self.declare_parameter("transcript_topic", "/whisper_transcript")
        self.declare_parameter("vlm_topic", "/smolvlm/output")
        self.declare_parameter("recognized_faces_topic", "/recognized_faces")
        self.declare_parameter("use_face_detections", True)

        self.declare_parameter("response_topic", "/openai_response")
        # Publish stops onto the social mux input by default.
        self.declare_parameter("cmd_vel_topic", "/cmd_vel_social")

        self.declare_parameter("state_topic", "/social_skill/state")
        self.declare_parameter("event_topic", "/social_skill/event")
        self.declare_parameter("active_skill_topic", "/social_skill/active_skill")

        self.declare_parameter("openai_service", "/openai_ask")

        self.declare_parameter("language", "de")
        self.declare_parameter("reset_conversation", True)

        self.declare_parameter("auto_greet_enabled", False)
        self.declare_parameter("auto_wave_response_enabled", False)
        self.declare_parameter("require_person_for_auto_greet", True)
        self.declare_parameter("greet_cooldown_sec", 30.0)
        self.declare_parameter("interaction_timeout_sec", 25.0)

        self.declare_parameter("enable_motion", False)
        self.declare_parameter("stop_motion_on_stop_command", True)

        self.declare_parameter("robot_name", "Pepper")
        self.declare_parameter("project_name", "Architektur sozialer Fähigkeiten")

        self.declare_parameter(
            "system_prompt",
            (
                "Du bist Pepper, ein humanoider sozialer Roboter. "
                "Du bist Teil des Projekts Architektur sozialer Fähigkeiten. "
                "Antworte immer auf Deutsch. "
                "Antworte kurz, klar und natürlich, damit die Antwort gut gesprochen werden kann. "
                "Nutze den Kamerakontext natürlich, wenn er verfügbar ist. "
                "Sage nicht, dass du eine visuelle Beschreibung erhalten hast. "
                "Sei höflich, sozial aufmerksam und verständlich."
            ),
        )

        self.transcript_topic = self.get_parameter("transcript_topic").value
        self.vlm_topic = self.get_parameter("vlm_topic").value
        self.recognized_faces_topic = self.get_parameter("recognized_faces_topic").value
        self.use_face_detections = bool(self.get_parameter("use_face_detections").value)

        self.response_topic = self.get_parameter("response_topic").value
        self.cmd_vel_topic = self.get_parameter("cmd_vel_topic").value

        self.state_topic = self.get_parameter("state_topic").value
        self.event_topic = self.get_parameter("event_topic").value
        self.active_skill_topic = self.get_parameter("active_skill_topic").value

        self.openai_service = self.get_parameter("openai_service").value

        self.language = self.get_parameter("language").value
        self.reset_conversation = bool(self.get_parameter("reset_conversation").value)

        self.auto_greet_enabled = bool(self.get_parameter("auto_greet_enabled").value)
        self.auto_wave_response_enabled = bool(
            self.get_parameter("auto_wave_response_enabled").value
        )
        self.require_person_for_auto_greet = bool(
            self.get_parameter("require_person_for_auto_greet").value
        )
        self.greet_cooldown_sec = float(self.get_parameter("greet_cooldown_sec").value)
        self.interaction_timeout_sec = float(
            self.get_parameter("interaction_timeout_sec").value
        )

        self.enable_motion = bool(self.get_parameter("enable_motion").value)
        self.stop_motion_on_stop_command = bool(
            self.get_parameter("stop_motion_on_stop_command").value
        )

        self.robot_name = self.get_parameter("robot_name").value
        self.project_name = self.get_parameter("project_name").value
        self.system_prompt = self.get_parameter("system_prompt").value

        self.latest_vlm = ""
        self.latest_transcript = ""
        self.latest_faces = []

        self.state = SocialState.IDLE
        self.active_skill = "idle"

        self.last_interaction_time = 0.0
        self.last_greet_time = 0.0
        self.last_person_seen_time = 0.0

        self.pending_llm_request = False

        self.sub_transcript = self.create_subscription(
            String,
            self.transcript_topic,
            self.transcript_callback,
            10,
        )

        self.sub_vlm = self.create_subscription(
            String,
            self.vlm_topic,
            self.vlm_callback,
            10,
        )

        self.sub_faces = self.create_subscription(
            String,
            self.recognized_faces_topic,
            self.faces_callback,
            10,
        )

        self.pub_response = self.create_publisher(
            String,
            self.response_topic,
            10,
        )

        self.pub_state = self.create_publisher(
            String,
            self.state_topic,
            10,
        )

        self.pub_event = self.create_publisher(
            String,
            self.event_topic,
            10,
        )

        self.pub_active_skill = self.create_publisher(
            String,
            self.active_skill_topic,
            10,
        )

        self.pub_cmd_vel = self.create_publisher(
            Twist,
            self.cmd_vel_topic,
            10,
        )

        self.openai_client = self.create_client(OpenaiServer, self.openai_service)

        self.create_timer(1.0, self.timer_callback)

        self.publish_state(SocialState.IDLE, "idle")
        self.publish_event("system_started", "Social Skill Manager wurde gestartet.")

        self.get_logger().info("Pepper Social Skill Manager läuft.")
        self.get_logger().info(f"Transcript Topic: {self.transcript_topic}")
        self.get_logger().info(f"VLM Topic: {self.vlm_topic}")
        self.get_logger().info(f"Faces Topic: {self.recognized_faces_topic}")
        self.get_logger().info(f"Response Topic: {self.response_topic}")
        self.get_logger().info(f"cmd_vel Topic: {self.cmd_vel_topic}")
        self.get_logger().info(f"OpenAI Service: {self.openai_service}")

    def normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\säöüß]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def contains_any(self, text: str, keywords) -> bool:
        normalized = self.normalize(text)
        return any(k in normalized for k in keywords)

    def extract_vlm_field(self, vlm_text: str, field_name: str) -> str:
        pattern = rf"(?im)^\s*{field_name}\s*[:\-]\s*(.+?)\s*$"
        match = re.search(pattern, vlm_text or "")

        if not match:
            return ""

        return match.group(1).strip()

    def parse_vlm_context(self, vlm_text: str) -> dict:
        """Parse the structured output produced by pepper_vlm_node.

        Expected schema:
          PERSON: male|female|unknown|none
          GESTURE: open label, e.g. waving, pointing, looking_at_robot, none
          EMOTION: open label, e.g. happy, neutral, unknown
          SCENE: German sentence
        """
        person = self.extract_vlm_field(vlm_text, "PERSON").lower().strip()
        gesture = self.extract_vlm_field(vlm_text, "GESTURE").lower().strip()
        emotion = self.extract_vlm_field(vlm_text, "EMOTION").lower().strip()
        scene = self.extract_vlm_field(vlm_text, "SCENE").strip()

        person = person.replace(" ", "_")
        gesture = gesture.replace(" ", "_")
        emotion = emotion.replace(" ", "_")

        if person in ["yes", "visible", "person_visible"]:
            person = "unknown"
        elif person in ["no", "not_visible", "no_person", "none_visible"]:
            person = "none"

        if not person:
            person = "unknown" if self.contains_any(
                vlm_text,
                ["mann", "frau", "mensch", "person", "gesicht", "hand", "arm", "man", "woman", "face", "human"],
            ) else "none"

        if not gesture:
            gesture = "unknown" if person != "none" else "none"

        if not emotion:
            emotion = "unknown"

        if not scene:
            scene = ""

        return {
            "person": person,
            "gesture": gesture,
            "emotion": emotion,
            "scene": scene,
        }

    def faces_callback(self, msg: String):
        if not self.use_face_detections:
            return

        text = (msg.data or "").strip()
        if not text:
            self.latest_faces = []
            return

        try:
            payload = json.loads(text)
            faces = payload.get("faces", [])
            if not isinstance(faces, list):
                faces = []
            self.latest_faces = faces
            if faces:
                self.last_person_seen_time = time.time()
        except Exception as exc:
            self.get_logger().warn(f"Failed to parse /recognized_faces: {exc}")
            self.latest_faces = []

    def primary_face(self) -> dict:
        if not self.latest_faces:
            return {}
        return self.latest_faces[0] if isinstance(self.latest_faces[0], dict) else {}

    def face_person_label(self) -> str:
        face = self.primary_face()
        gender = str(face.get("gender", "")).lower().strip()
        if gender in ["male", "man", "männlich"]:
            return "male"
        if gender in ["female", "woman", "weiblich"]:
            return "female"
        if self.latest_faces:
            return "unknown"
        return "none"

    def face_emotion_label(self) -> str:
        face = self.primary_face()
        emotion = str(
            face.get("dominant_expression")
            or face.get("emotion")
            or face.get("expression")
            or ""
        ).lower().strip().replace(" ", "_")
        return emotion or "unknown"

    def detect_person(self, vlm_text: str) -> bool:
        if self.use_face_detections and self.latest_faces:
            return True
        ctx = self.parse_vlm_context(vlm_text)
        return ctx["person"] in ["male", "female", "unknown"]

    def detect_wave(self, vlm_text: str) -> bool:
        ctx = self.parse_vlm_context(vlm_text)
        gesture = ctx["gesture"]

        wave_like_gestures = [
            "waving",
            "wave",
            "raised_hand",
            "hand_raised",
            "open_palm",
            "hand_up",
        ]

        if gesture in wave_like_gestures:
            return True

        normalized_scene = self.normalize(ctx.get("scene", ""))
        return any(
            keyword in normalized_scene
            for keyword in ["winkt", "winken", "hand gehoben", "gehobene hand", "hand hoch"]
        )

    def detect_emotion_hint(self, vlm_text: str) -> str:
        emotion_map = {
            "happy": "positiv",
            "smiling": "positiv",
            "neutral": "neutral",
            "sad": "traurig",
            "angry": "frustriert",
            "annoyed": "frustriert",
            "confused": "verwirrt",
            "surprised": "überrascht",
            "tired": "müde",
            "sleepy": "müde",
        }

        if self.use_face_detections:
            face_emotion = self.face_emotion_label()
            if face_emotion in emotion_map:
                return emotion_map[face_emotion]

        ctx = self.parse_vlm_context(vlm_text)
        emotion = ctx["emotion"]

        if emotion in emotion_map:
            return emotion_map[emotion]

        normalized = self.normalize(vlm_text)

        if any(word in normalized for word in ["happy", "smiling", "smile", "glücklich", "lächelt", "lächeln"]):
            return "positiv"
        if any(word in normalized for word in ["sad", "upset", "crying", "traurig", "weint"]):
            return "traurig"
        if any(word in normalized for word in ["confused", "uncertain", "puzzled", "verwirrt", "unsicher"]):
            return "verwirrt"
        if any(word in normalized for word in ["angry", "annoyed", "frustrated", "wütend", "genervt", "frustriert"]):
            return "frustriert"

        return "unbekannt"

    def format_vlm_for_speech(self, vlm_text: str) -> str:
        ctx = self.parse_vlm_context(vlm_text)
        scene = ctx.get("scene", "").strip()

        if not scene or scene.lower() in ["unknown", "none"]:
            scene = "Ich habe im Moment keine zuverlässige Kamerabeschreibung."

        person = ctx["person"]
        emotion = ctx["emotion"]
        if self.use_face_detections and self.latest_faces:
            face_person = self.face_person_label()
            if face_person != "none":
                person = face_person
            face_emotion = self.face_emotion_label()
            if face_emotion != "unknown":
                emotion = face_emotion

        hints = [
            f"Person: {person}",
            f"Geste: {ctx['gesture'] or 'unknown'}",
            f"Emotion: {emotion or 'unknown'}",
        ]
        if self.use_face_detections and self.latest_faces:
            hints.append(f"Gesichter: {len(self.latest_faces)}")

        return f"{scene} Erkannte Hinweise: {', '.join(hints)}."

    def vlm_callback(self, msg: String):
        text = msg.data.strip()
        if not text:
            return

        self.latest_vlm = text

        person_detected = self.detect_person(text)
        wave_detected = self.detect_wave(text)

        if person_detected:
            self.last_person_seen_time = time.time()
        
        if not self.auto_greet_enabled and not self.auto_wave_response_enabled:
            return

        if self.auto_wave_response_enabled and wave_detected:
            self.handle_auto_greeting(person_detected, wave_detected, text)
            return
            
        if self.auto_greet_enabled:
            self.handle_auto_greeting(person_detected, wave_detected, text)

    def handle_auto_greeting(self, person_detected: bool, wave_detected: bool, vlm_text: str):
        now = time.time()

        if now - self.last_greet_time < self.greet_cooldown_sec:
            return

        if self.require_person_for_auto_greet and not person_detected:
            return

        if wave_detected:
            self.last_greet_time = now
            self.last_interaction_time = now
            self.publish_state(SocialState.GREETING, "gesture_greeting")
            self.publish_event("wave_detected", vlm_text)
            self.publish_response(
                "Hallo, ich sehe, dass du winkst. Ich bin Pepper. Wie kann ich dir helfen?"
            )
            return

        if person_detected and self.state == SocialState.IDLE:
            self.last_greet_time = now
            self.last_interaction_time = now
            self.publish_state(SocialState.PERSON_DETECTED, "person_detection")
            self.publish_event("person_detected", vlm_text)
            self.publish_response(
                "Hallo, ich bin Pepper. Ich kann mit dir sprechen, beschreiben was ich sehe, und dieses Projekt erklären."
            )

    def transcript_callback(self, msg: String):
        text = msg.data.strip()
        if not text:
            return

        self.latest_transcript = text
        self.last_interaction_time = time.time()

        self.publish_event("user_transcript", text)
        self.publish_state(SocialState.LISTENING, "transcript_received")

        command = self.normalize(text)

        if self.is_stop_command(command):
            self.handle_stop_command()
            return

        if self.is_goodbye_command(command):
            self.handle_goodbye()
            return

        if self.is_help_command(command):
            self.handle_help()
            return

        if self.is_project_command(command):
            self.handle_project_explanation()
            return

        if self.is_visual_question(command):
            self.handle_visual_question()
            return

        if self.is_intro_command(command):
            self.handle_introduction()
            return

        self.handle_general_conversation(text)

    def is_stop_command(self, command: str) -> bool:
        stop_phrases = [
            "stop",
            "stopp",
            "halte an",
            "hör auf",
            "abbrechen",
            "notstopp",
            "emergency stop",
            "halt",
        ]
        return any(phrase == command or phrase in command for phrase in stop_phrases)

    def is_goodbye_command(self, command: str) -> bool:
        goodbye_phrases = [
            "goodbye",
            "bye",
            "see you",
            "tschüss",
            "auf wiedersehen",
            "bis später",
            "danke pepper",
            "dankeschön pepper",
        ]
        return any(phrase in command for phrase in goodbye_phrases)

    def is_help_command(self, command: str) -> bool:
        help_phrases = [
            "what can you do",
            "help me",
            "your functions",
            "your abilities",
            "what are your skills",
            "was kannst du",
            "hilf mir",
            "deine funktionen",
            "deine fähigkeiten",
            "was sind deine fähigkeiten",
        ]
        return any(phrase in command for phrase in help_phrases)

    def is_project_command(self, command: str) -> bool:
        project_phrases = [
            "explain the project",
            "what is this project",
            "architecture of social skills",
            "architektur sozialer fähigkeiten",
            "social skills project",
            "tell me about the project",
            "erkläre das projekt",
            "was ist dieses projekt",
            "erzähl mir über das projekt",
        ]
        return any(phrase in command for phrase in project_phrases)

    def is_visual_question(self, command: str) -> bool:
        visual_phrases = [
            "what do you see",
            "describe the scene",
            "what is in front of you",
            "who is there",
            "can you see me",
            "what is happening",
            "was siehst du",
            "beschreibe die szene",
            "was ist vor dir",
            "wer ist da",
            "kannst du mich sehen",
            "was passiert hier",
        ]
        return any(phrase in command for phrase in visual_phrases)

    def is_intro_command(self, command: str) -> bool:
        intro_phrases = [
            "introduce yourself",
            "who are you",
            "tell me about yourself",
            "what is your name",
            "stell dich vor",
            "wer bist du",
            "erzähl mir etwas über dich",
            "wie heißt du",
        ]
        return any(phrase in command for phrase in intro_phrases)

    def handle_stop_command(self):
        self.publish_state(SocialState.STOPPED, "safety_stop")
        self.publish_event("stop_command", self.latest_transcript)

        if self.stop_motion_on_stop_command:
            self.stop_motion()

        self.publish_response("Ich habe gestoppt. Ich warte auf deine nächste Anweisung.")

    def handle_goodbye(self):
        self.publish_state(SocialState.GOODBYE, "goodbye")
        self.publish_event("goodbye", self.latest_transcript)
        self.publish_response("Auf Wiedersehen. Es war schön, mit dir zu interagieren.")
        self.create_timer_once(3.0, self.return_to_idle)

    def handle_help(self):
        self.publish_state(SocialState.SPEAKING, "help_skill")
        self.publish_event("help_requested", self.latest_transcript)

        text = (
            "Ich kann Menschen begrüßen, auf Winken reagieren, Fragen beantworten, "
            "beschreiben was ich sehe, das Projekt Architektur sozialer Fähigkeiten erklären "
            "und Mensch-Roboter-Interaktionen demonstrieren."
        )
        self.publish_response(text)

    def handle_project_explanation(self):
        self.publish_state(SocialState.SPEAKING, "project_explanation")
        self.publish_event("project_explanation_requested", self.latest_transcript)

        text = (
            "Dieses Projekt heißt Architektur sozialer Fähigkeiten. "
            "Es verbindet Spracherkennung, visuelle Wahrnehmung, Sprachmodell-basiertes Denken, "
            "Sprachausgabe, Roboterzustände und Dashboard-Visualisierung in einer ROS 2 Architektur. "
            "Das Ziel ist, dass Pepper nicht nur wie ein einfacher Chatbot reagiert, "
            "sondern sozial bewusster mit Menschen interagiert."
        )
        self.publish_response(text)

    def handle_visual_question(self):
        self.publish_state(SocialState.SPEAKING, "visual_explanation")
        self.publish_event("visual_question", self.latest_transcript)

        if self.latest_vlm:
            text = self.format_vlm_for_speech(self.latest_vlm)
        else:
            text = "Ich habe im Moment noch keine aktuelle Kamerabeschreibung."

        self.publish_response(text)

    def handle_introduction(self):
        self.publish_state(SocialState.SPEAKING, "introduction")
        self.publish_event("introduction_requested", self.latest_transcript)

        text = (
            f"Mein Name ist {self.robot_name}. "
            f"Ich bin ein humanoider Roboter mit einem ROS 2 System für soziale Interaktion. "
            f"Mein aktuelles Projekt heißt {self.project_name}."
        )
        self.publish_response(text)

    def handle_general_conversation(self, user_text: str):
        self.publish_state(SocialState.THINKING, "conversation")
        self.publish_event("llm_request", user_text)

        prompt = self.build_social_prompt(user_text)

        if not self.openai_client.wait_for_service(timeout_sec=0.5):
            self.publish_response(
                "Der Sprachmodell-Dienst ist im Moment nicht verfügbar."
            )
            self.publish_state(SocialState.IDLE, "idle")
            return

        req = OpenaiServer.Request()
        req.prompt = prompt
        req.pre_prompt = self.system_prompt
        req.reset_conversation = self.reset_conversation

        self.pending_llm_request = True

        future = self.openai_client.call_async(req)
        future.add_done_callback(self.openai_response_callback)

    def build_social_prompt(self, user_text: str) -> str:
        parts = []

        parts.append("[Gesprochene Eingabe des Benutzers]")
        parts.append(user_text)

        if self.latest_vlm:
            ctx = self.parse_vlm_context(self.latest_vlm)
            parts.append("\n[Kamerakontext des Roboters]")
            parts.append(self.latest_vlm)
            parts.append("\n[Geparste visuelle Hinweise]")
            parts.append(json.dumps(ctx, ensure_ascii=False))

        if self.use_face_detections and self.latest_faces:
            face = self.primary_face()
            parts.append("\n[Gesichtserkennung]")
            parts.append(
                json.dumps(
                    {
                        "faces_detected": len(self.latest_faces),
                        "primary_user_id": face.get("user_id"),
                        "primary_gender": face.get("gender"),
                        "primary_expression": face.get("dominant_expression")
                        or face.get("emotion")
                        or face.get("expression"),
                        "is_new": face.get("is_new"),
                    },
                    ensure_ascii=False,
                )
            )

        emotion_hint = self.detect_emotion_hint(self.latest_vlm)
        if emotion_hint != "unbekannt":
            parts.append("\n[Erkannter sozialer Hinweis]")
            parts.append(emotion_hint)

        parts.append("\n[Anweisung]")
        parts.append(
            "Antworte als Pepper auf Deutsch und sozial passend. "
            "Nutze die Kameradaten nur, wenn sie für die Antwort relevant sind. "
            "Sage nicht 'in diesem Bild' oder 'das Bild zeigt'. "
            "Behandle PERSON: male/female nur als visuelle Schätzung. "
            "Halte die Antwort kurz genug für eine gesprochene Mensch-Roboter-Interaktion."
        )

        return "\n".join(parts)

    def openai_response_callback(self, future):
        self.pending_llm_request = False

        try:
            response = future.result()
            text = response.response.strip()

            if not text:
                text = "Entschuldigung, ich konnte keine Antwort erzeugen."

            self.publish_state(SocialState.SPEAKING, "conversation")
            self.publish_response(text)
            self.publish_event("llm_response", text)

        except Exception as exc:
            self.get_logger().error(f"OpenAI service call failed: {exc}")
            self.publish_response(
                "Entschuldigung, der Sprachmodell-Dienst ist fehlgeschlagen."
            )
            self.publish_state(SocialState.IDLE, "idle")

    def publish_response(self, text: str):
        if not text:
            return

        msg = String()
        msg.data = text
        self.pub_response.publish(msg)

        self.publish_state(SocialState.SPEAKING, self.active_skill)

        self.get_logger().info(f"Pepper Antwort: {text}")

    def publish_state(self, state: SocialState, active_skill: str):
        self.state = state
        self.active_skill = active_skill

        state_payload = {
            "state": self.state.value,
            "active_skill": self.active_skill,
            "timestamp": time.time(),
        }

        state_msg = String()
        state_msg.data = json.dumps(state_payload, ensure_ascii=False)
        self.pub_state.publish(state_msg)

        skill_msg = String()
        skill_msg.data = self.active_skill
        self.pub_active_skill.publish(skill_msg)

    def publish_event(self, event_type: str, detail: str):
        payload = {
            "event": event_type,
            "detail": detail,
            "state": self.state.value,
            "active_skill": self.active_skill,
            "timestamp": time.time(),
        }

        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.pub_event.publish(msg)

        self.get_logger().info(f"Social event: {event_type} | {detail}")

    def stop_motion(self):
        twist = Twist()
        twist.linear.x = 0.0
        twist.linear.y = 0.0
        twist.linear.z = 0.0
        twist.angular.x = 0.0
        twist.angular.y = 0.0
        twist.angular.z = 0.0
        self.pub_cmd_vel.publish(twist)
        self.get_logger().info(f"Zero velocity wurde an {self.cmd_vel_topic} gesendet.")

    def timer_callback(self):
        now = time.time()

        if self.state == SocialState.IDLE:
            return

        if self.pending_llm_request:
            return

        elapsed = now - self.last_interaction_time

        if elapsed > self.interaction_timeout_sec:
            self.return_to_idle()

    def return_to_idle(self):
        self.publish_state(SocialState.IDLE, "idle")
        self.publish_event("return_to_idle", "Interaktion beendet oder Timeout erreicht.")

    def create_timer_once(self, delay_sec: float, callback):
        timer_holder = {"timer": None}

        def wrapped():
            timer_holder["timer"].cancel()
            callback()

        timer_holder["timer"] = self.create_timer(delay_sec, wrapped)
        return timer_holder["timer"]


def main(args=None):
    rclpy.init(args=args)
    node = SocialSkillManager()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_motion()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
