#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

from flask import Flask, Response, render_template_string, request, jsonify
import threading
import time
import os
import cv2

# Ensure Flask looks in the actual module path for "static" folder
import pepper_dashboard
static_path = os.path.join(os.path.dirname(pepper_dashboard.__file__), 'static')
app = Flask(__name__, static_folder=static_path, static_url_path='/static')

# Global state to share between ROS and Flask
state = {
    "status": "IDLE",
    "transcript": "",
    "vlm_desc": "",
    "response": "",
    "battery": 85,  # Default fallback if topic isnt available
    "last_update": time.time()
}

# Latest camera frame
latest_frame = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
    <title>Pepper Robot Dashboard</title>
    <style>
        body {
            margin: 0; padding: 0;
            background-color: #f0f4f8; color: #1e293b;
            font-family: Arial, Helvetica, sans-serif;
            height: 100vh; width: 100vw;
            display: flex; flex-direction: column;
            overflow: hidden;
            box-sizing: border-box;
        }
        
        * { box-sizing: border-box; }

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
        }

        .right-col {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 30px;
            height: 100%;
        }

        .card {
            background-color: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border: 1px solid #cbd5e1;
            display: flex;
            flex-direction: column;
        }

        .video-container {
            padding: 0px;
            flex: 1.5 1 auto;
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
            min-height: 570px;
        }

        .card-row {
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .card-title {
            font-size: 24px;
            font-weight: bold;
            color: #0f172a;
            margin-bottom: 12px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 8px;
        }

        .card-text {
            font-size: 20px;
            line-height: 1.6;
            color: #334155;
            white-space: pre-wrap;
            flex: 1;
            overflow-y: auto;
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
    </style>
</head>
<body>
    <div class="header">
        <div class="header-logo left">
            <img src="/static/left_logo.png?v={{ cache_buster }}" alt="Left Logo" onerror="this.style.display='none'">
        </div>
        <div class="header-center">
            <div class="header-title">Pepper Robot Dashboard</div>
            <div class="header-status">Robot State: <span id="statusBadge">Active</span></div>
        </div>
        <div class="header-logo right">
            <img src="/static/right_logo.png?v={{ cache_buster }}" alt="Right Logo" onerror="this.style.display='none'">
        </div>
    </div>

    <div class="main-content">
        <div class="left-col">
            <div class="card video-container">
                <img src="/camera_feed" alt="Robot Vision">
            </div>
            
            <div class="card desc-container">
                <div class="card-title">Image Description</div>
                <div id="vlmText" class="card-text">Waiting for vision input...</div>
            </div>
        </div>

        <div class="right-col">
            <div class="card card-row">
                <div class="card-title">ASR Response</div>
                <div id="asrText" class="card-text">Waiting for speech...</div>
            </div>
            
            <div class="card card-row">
                <div class="card-title">LLM Reasoning</div>
                <div id="reasoningText" class="card-text">Waiting for parsed input...</div>
            </div>

            <div class="card card-row">
                <div class="card-title">LLM Final Response</div>
                <div id="llmText" class="card-text">Waiting for response...</div>
            </div>
        </div>
    </div>

    <div class="bottom-bar">
        <div id="clockDisplay">2026-03-27 12:15:33</div>
        <div class="battery-container">
            <div class="battery-outline">
                <div id="batteryFill" class="battery-fill"></div>
            </div>
            <span id="batteryText">85%</span>
        </div>
    </div>

    <script>
        // Use basic JS 1.7 AJAX polling
        function updateState() {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", "/state", true);
            xhr.onreadystatechange = function() {
                if (xhr.readyState == 4 && xhr.status == 200) {
                    try {
                        var data = window.JSON ? window.JSON.parse(xhr.responseText) : eval('(' + xhr.responseText + ')');
                        
                        document.getElementById("vlmText").innerHTML = data.vlm_desc || "Waiting for vision input...";
                        document.getElementById("asrText").innerHTML = data.transcript || "Waiting for speech...";
                        
                        // Construct the LLM Reasoning box logic
                        var reasoningStr = "Waiting for parsed input...";
                        if (data.transcript || data.vlm_desc) {
                            var vlm = data.vlm_desc || "None";
                            var user = data.transcript || "None";
                            reasoningStr = "<b>Visual Context:</b><br>" + vlm + "<br><br><b>User Question:</b><br>" + user;
                        }
                        document.getElementById("reasoningText").innerHTML = reasoningStr;

                        document.getElementById("llmText").innerHTML = data.response || "Waiting for response...";
                        document.getElementById("statusBadge").innerHTML = data.status;
                        
                        
                        // Parse battery info if available
                        if (data.battery !== undefined) {
                            document.getElementById("batteryText").innerHTML = data.battery + "%";
                            document.getElementById("batteryFill").style.width = data.battery + "%";
                            if(data.battery <= 20) {
                                document.getElementById("batteryFill").style.backgroundColor = "#ef4444"; // red
                            } else {
                                document.getElementById("batteryFill").style.backgroundColor = "#4ade80"; // green
                            }
                        }
                    } catch(e) {}
                }
            };
            xhr.send();
        }
        
        function updateClock() {
            var now = new Date();
            var year = now.getFullYear();
            var month = String(now.getMonth() + 1).padStart(2, '0');
            var day = String(now.getDate()).padStart(2, '0');
            var hours = String(now.getHours()).padStart(2, '0');
            var minutes = String(now.getMinutes()).padStart(2, '0');
            var seconds = String(now.getSeconds()).padStart(2, '0');
            document.getElementById("clockDisplay").innerHTML = year + "-" + month + "-" + day + " " + hours + ":" + minutes + ":" + seconds;
        }

        setInterval(updateState, 500);
        setInterval(updateClock, 1000);
        updateClock(); // Initial call

    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, cache_buster=int(time.time()))

@app.route('/state')
def get_state():
    return jsonify(state)

@app.route('/battery', methods=['POST'])
def update_battery():
    try:
        val = request.form.get('battery')
        if val is not None:
            state["battery"] = int(val)
    except:
        pass
    return "OK", 200

def generate_mjpeg():
    global latest_frame
    while True:
        if latest_frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.1)

@app.route('/camera_feed')
def camera_feed():
    return Response(generate_mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')


class DashboardNode(Node):
    def __init__(self):
        super().__init__('pepper_dashboard_node')
        
        self.bridge = CvBridge()
        
        self.sub_audio = self.create_subscription(String, 'pepper_audio', self.audio_callback, 10)
        self.sub_transcript = self.create_subscription(String, 'whisper_transcript', self.transcript_callback, 10)
        self.sub_response = self.create_subscription(String, 'openai_response', self.response_callback, 10)
        self.sub_camera = self.create_subscription(Image, '/camera/front/image_raw', self.camera_callback, 10)
        self.sub_vlm = self.create_subscription(String, '/smolvlm/output', self.vlm_callback, 10)

        
        self.get_logger().info("Dashboard node ready. Monitoring ROS topics...")

    def camera_callback(self, msg):
        global latest_frame
        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            ret, jpeg = cv2.imencode('.jpg', cv_image, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            if ret:
                latest_frame = jpeg.tobytes()
        except Exception as e:
            self.get_logger().error(f"Image processing error: {e}")

    def vlm_callback(self, msg):
        state["vlm_desc"] = msg.data

    def audio_callback(self, msg):
        if state["status"] in ["IDLE", "LISTENING"]:
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
        
    def reset_idle_timer(self):
        state["last_update"] = time.time()

def ros_thread():
    rclpy.init()
    node = DashboardNode()
    
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.5)
        
        if time.time() - state["last_update"] > 10.0 and state["status"] != "IDLE":
            state["status"] = "IDLE"
            
    node.destroy_node()
    rclpy.shutdown()

def main(args=None):
    t = threading.Thread(target=ros_thread)
    t.daemon = True
    t.start()
    
    print("Starting Flask dashboard on 0.0.0.0:5000...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
