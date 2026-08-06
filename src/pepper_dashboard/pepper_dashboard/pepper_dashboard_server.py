#!/usr/bin/env python3

import os
import threading
import time

import cv2
import rclpy
from cv_bridge import CvBridge
from flask import Flask, Response, jsonify, render_template_string, request
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String

# Ensure Flask looks in the actual module path for the "static" folder.
import pepper_dashboard

static_path = os.path.join(os.path.dirname(pepper_dashboard.__file__), "static")
app = Flask(__name__, static_folder=static_path, static_url_path="/static")

# Global state shared between ROS and Flask.
state = {
    "status": "IDLE",
    "transcript": "",
    "vlm_desc": "",
    "face_context": "",
    "response": "",
    "social_state": "IDLE",
    "active_skill": "idle",
    "social_event": "",
    "battery": 85,
    "last_update": time.time(),
}

# Latest camera frame encoded as JPEG bytes.
latest_frame = None
latest_frame_time = 0.0
latest_frame_count = 0
frame_lock = threading.Lock()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
    <title>Pepper Robot Dashboard</title>

    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #f0f4f8;
            color: #1e293b;
            font-family: Arial, Helvetica, sans-serif;
            height: 100vh;
            width: 100vw;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-sizing: border-box;
        }

        * {
            box-sizing: border-box;
        }

        .header {
            background-color: #00af73;
            color: white;
            padding: 20px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 3px solid #008f5e;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            position: relative;
        }

        .header-center {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            flex: 1;
        }

        .header-logo {
            display: flex;
            align-items: center;
            height: 70px;
            width: 280px;
        }

        .header-logo.left {
            justify-content: flex-start;
        }

        .header-logo.right {
            justify-content: flex-end;
        }

        .header-logo img {
            max-height: 100%;
            max-width: 100%;
            object-fit: contain;
            background-color: transparent;
        }

        .header-title {
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .header-status {
            font-size: 24px;
        }

        .main-content {
            display: flex;
            flex: 1;
            padding: 30px;
            gap: 30px;
            overflow: hidden;
            background-color: #f1f5f9;
        }

        .left-col {
            flex: 1.6;
            display: flex;
            flex-direction: column;
            gap: 30px;
            height: 100%;
            min-width: 0;
        }

        .right-col {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 20px;
            height: 100%;
            min-width: 0;
        }

        .card {
            background-color: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #cbd5e1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }

        .video-container {
            padding: 0;
            flex: 1.4 1 auto;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            background-color: #000;
            border: 2px solid #000;
        }

        .video-container img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            border-radius: 8px;
        }

        .desc-container {
            flex: 1 1 auto;
            min-height: 260px;
        }

        .card-row {
            flex: 1;
            min-height: 0;
        }

        .card-title {
            font-size: 22px;
            font-weight: bold;
            color: #0f172a;
            margin-bottom: 12px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 8px;
        }

        .card-text {
            font-size: 18px;
            line-height: 1.5;
            color: #334155;
            white-space: pre-wrap;
            flex: 1;
            overflow-y: auto;
            word-break: break-word;
        }

        .bottom-bar {
            background-color: #333;
            color: white;
            padding: 12px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 18px;
        }

        .battery-container {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .battery-outline {
            width: 60px;
            height: 24px;
            border: 3px solid white;
            border-radius: 4px;
            padding: 2px;
            position: relative;
        }

        .battery-outline::after {
            content: '';
            position: absolute;
            right: -6px;
            top: 4px;
            width: 4px;
            height: 10px;
            background: white;
            border-radius: 0 2px 2px 0;
        }

        .battery-fill {
            height: 100%;
            background-color: #4ade80;
            width: 85%;
            border-radius: 2px;
            transition: width 0.3s;
        }

        .status-pill {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            border: 1px solid rgba(255,255,255,0.4);
            border-radius: 999px;
            padding: 4px 14px;
        }
    </style>
</head>

<body>
    <div class="header">
        <div class="header-logo left">
            <img src="/static/left_logo.png?v={{ cache_buster }}" alt="Left Logo" onerror="this.style.display='none'">
        </div>

        <div class="header-center">
            <div class="header-title">Pepper Robot Dashboard</div>
            <div class="header-status">
                Robot State:
                <span id="statusBadge" class="status-pill">IDLE</span>
            </div>
        </div>

        <div class="header-logo right">
            <img src="/static/right_logo.png?v={{ cache_buster }}" alt="Right Logo" onerror="this.style.display='none'">
        </div>
    </div>

    <div class="main-content">
        <div class="left-col">
            <div class="card video-container">
                <img id="cameraImage" src="/camera_feed?ts={{ cache_buster }}" alt="Robot Vision">
            </div>

            <div class="card desc-container">
                <div class="card-title">Image Description</div>
                <div id="vlmText" class="card-text">Waiting for vision input...</div>
            </div>
        </div>

        <div class="right-col">
            <div class="card card-row">
                <div class="card-title">ASR Transcript</div>
                <div id="asrText" class="card-text">Waiting for speech...</div>
            </div>

            <div class="card card-row">
                <div class="card-title">LLM Reasoning Context</div>
                <div id="reasoningText" class="card-text">Waiting for parsed input...</div>
            </div>

            <div class="card card-row">
                <div class="card-title">LLM Final Response</div>
                <div id="llmText" class="card-text">Waiting for response...</div>
            </div>

            <div class="card card-row">
                <div class="card-title">Social Skill State</div>
                <div id="socialSkillText" class="card-text">Waiting for social skill...</div>
            </div>
        </div>
    </div>

    <div class="bottom-bar">
        <div id="clockDisplay">0000-00-00 00:00:00</div>

        <div class="battery-container">
            <div class="battery-outline">
                <div id="batteryFill" class="battery-fill"></div>
            </div>
            <span id="batteryText">85%</span>
        </div>
    </div>

    <script>
        function escapeHtml(value) {
            if (value === null || value === undefined) {
                return "";
            }

            return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function formatJsonString(value) {
            if (!value) {
                return "";
            }

            try {
                var obj = JSON.parse(value);
                return escapeHtml(JSON.stringify(obj, null, 2));
            } catch (e) {
                return escapeHtml(value);
            }
        }

        function updateState() {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", "/state", true);

            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4 && xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);

                        var vlm = data.vlm_desc || "";
                        var faceContext = data.face_context || "";
                        var transcript = data.transcript || "";
                        var response = data.response || "";

                        document.getElementById("vlmText").innerHTML =
                            vlm ? escapeHtml(vlm) : "Waiting for vision input...";

                        document.getElementById("asrText").innerHTML =
                            transcript ? escapeHtml(transcript) : "Waiting for speech...";

                        var reasoningStr = "Waiting for parsed input...";
                        if (transcript || vlm || faceContext) {
                            reasoningStr =
                                "<b>Scene Description:</b><br>" +
                                escapeHtml(vlm || "None") +
                                "<br><br><b>Face Perception:</b><br>" +
                                formatJsonString(faceContext || "None") +
                                "<br><br><b>User Question:</b><br>" +
                                escapeHtml(transcript || "None");
                        }

                        document.getElementById("reasoningText").innerHTML = reasoningStr;

                        document.getElementById("llmText").innerHTML =
                            response ? escapeHtml(response) : "Waiting for response...";

                        document.getElementById("statusBadge").innerHTML =
                            escapeHtml(data.status || "IDLE");

                        var socialText =
                            "<b>Active Skill:</b><br>" +
                            escapeHtml(data.active_skill || "idle") +
                            "<br><br><b>State:</b><br>" +
                            formatJsonString(data.social_state || "IDLE") +
                            "<br><br><b>Last Event:</b><br>" +
                            formatJsonString(data.social_event || "None");

                        document.getElementById("socialSkillText").innerHTML = socialText;

                        if (data.battery !== undefined) {
                            var battery = parseInt(data.battery);
                            if (isNaN(battery)) {
                                battery = 85;
                            }

                            if (battery < 0) {
                                battery = 0;
                            }

                            if (battery > 100) {
                                battery = 100;
                            }

                            document.getElementById("batteryText").innerHTML = battery + "%";
                            document.getElementById("batteryFill").style.width = battery + "%";

                            if (battery <= 20) {
                                document.getElementById("batteryFill").style.backgroundColor = "#ef4444";
                            } else {
                                document.getElementById("batteryFill").style.backgroundColor = "#4ade80";
                            }
                        }
                    } catch (e) {
                        console.log("Dashboard update failed:", e);
                    }
                }
            };

            xhr.send();
        }

        function updateClock() {
            var now = new Date();

            var year = now.getFullYear();
            var month = String(now.getMonth() + 1).padStart(2, "0");
            var day = String(now.getDate()).padStart(2, "0");
            var hours = String(now.getHours()).padStart(2, "0");
            var minutes = String(now.getMinutes()).padStart(2, "0");
            var seconds = String(now.getSeconds()).padStart(2, "0");

            document.getElementById("clockDisplay").innerHTML =
                year + "-" + month + "-" + day + " " + hours + ":" + minutes + ":" + seconds;
        }

        function reconnectCameraStream() {
            var img = document.getElementById("cameraImage");
            if (!img) {
                return;
            }

            // Pepper tablet WebView can sometimes drop long MJPEG streams.
            // Reload the stream URL periodically without reloading the full dashboard.
            img.src = "/camera_feed?ts=" + new Date().getTime();
        }

        setInterval(updateState, 500);
        setInterval(updateClock, 1000);
        setInterval(reconnectCameraStream, 30000);

        updateState();
        updateClock();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, cache_buster=int(time.time()))


@app.route("/state")
def get_state():
    return jsonify(state)


@app.route("/battery", methods=["POST"])
def update_battery():
    try:
        val = request.form.get("battery")
        if val is not None:
            battery = int(val)
            battery = max(0, min(100, battery))
            state["battery"] = battery
    except Exception:
        pass

    return "OK", 200


def make_placeholder_frame():
    image = 255 * (0 * cv2.UMat(240, 320, cv2.CV_8UC3).get())
    cv2.putText(
        image,
        "Waiting for camera...",
        (25, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    success, jpeg = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    return jpeg.tobytes() if success else b""


PLACEHOLDER_FRAME = make_placeholder_frame()


def generate_mjpeg():
    while True:
        with frame_lock:
            frame = latest_frame

        if frame is None:
            frame = PLACEHOLDER_FRAME

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Cache-Control: no-cache, no-store, must-revalidate\r\n"
            b"Pragma: no-cache\r\n"
            b"Expires: 0\r\n\r\n" +
            frame +
            b"\r\n"
        )

        # 10 FPS dashboard stream. This is enough for monitoring and keeps CPU load low.
        time.sleep(0.1)


@app.route("/camera_feed")
def camera_feed():
    response = Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        direct_passthrough=True,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Accel-Buffering"] = "no"
    return response


class DashboardNode(Node):
    def __init__(self):
        super().__init__("pepper_dashboard_node")

        self.bridge = CvBridge()

        self.sub_audio = self.create_subscription(
            String,
            "pepper_audio",
            self.audio_callback,
            10,
        )

        self.sub_transcript = self.create_subscription(
            String,
            "/whisper_transcript",
            self.transcript_callback,
            10,
        )

        self.sub_response = self.create_subscription(
            String,
            "/openai_response",
            self.response_callback,
            10,
        )

        camera_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
        )

        self.sub_camera = self.create_subscription(
            Image,
            "/camera/front/image_raw",
            self.camera_callback,
            camera_qos,
        )

        self.sub_vlm = self.create_subscription(
            String,
            "/smolvlm/output",
            self.vlm_callback,
            10,
        )

        self.sub_faces = self.create_subscription(
            String,
            "/recognized_faces",
            self.faces_callback,
            10,
        )

        self.sub_social_state = self.create_subscription(
            String,
            "/social_skill/state",
            self.social_state_callback,
            10,
        )

        self.sub_social_event = self.create_subscription(
            String,
            "/social_skill/event",
            self.social_event_callback,
            10,
        )

        self.sub_active_skill = self.create_subscription(
            String,
            "/social_skill/active_skill",
            self.active_skill_callback,
            10,
        )

        self.get_logger().info("Dashboard node ready. Monitoring ROS topics.")

    def camera_callback(self, msg):
        global latest_frame, latest_frame_time, latest_frame_count

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            success, jpeg = cv2.imencode(
                ".jpg",
                cv_image,
                [int(cv2.IMWRITE_JPEG_QUALITY), 65],
            )

            if success:
                with frame_lock:
                    latest_frame = jpeg.tobytes()
                    latest_frame_time = time.time()
                    latest_frame_count += 1

        except Exception as exc:
            self.get_logger().error(f"Image processing error: {exc}")

    def vlm_callback(self, msg):
        state["vlm_desc"] = msg.data
        self.reset_idle_timer()

    def faces_callback(self, msg):
        state["face_context"] = msg.data
        self.reset_idle_timer()

    def audio_callback(self, msg):
        if state["status"] in ["IDLE", "Listening..."]:
            state["status"] = "Listening..."
            self.reset_idle_timer()

    def transcript_callback(self, msg):
        state["transcript"] = msg.data
        state["status"] = "Processing AI Response..."
        self.reset_idle_timer()

    def response_callback(self, msg):
        state["response"] = msg.data
        state["status"] = "Speaking..."
        self.reset_idle_timer()

    def social_state_callback(self, msg):
        state["social_state"] = msg.data
        state["status"] = "Social Skill Active"
        self.reset_idle_timer()

    def social_event_callback(self, msg):
        state["social_event"] = msg.data
        self.reset_idle_timer()

    def active_skill_callback(self, msg):
        state["active_skill"] = msg.data
        self.reset_idle_timer()

    def reset_idle_timer(self):
        state["last_update"] = time.time()


def ros_thread():
    rclpy.init()
    node = DashboardNode()

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.5)

            if time.time() - state["last_update"] > 10.0 and state["status"] != "IDLE":
                state["status"] = "IDLE"

    finally:
        node.destroy_node()
        rclpy.shutdown()


def main(args=None):
    thread = threading.Thread(target=ros_thread)
    thread.daemon = True
    thread.start()

    print("Starting Flask dashboard on 0.0.0.0:5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
