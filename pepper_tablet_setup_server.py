#!/usr/bin/env python3

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from flask import Flask, request, redirect, jsonify


HOME = Path.home()
WORKSPACE = HOME / "pepper_ws"
LOG_DIR = WORKSPACE / "logs"
START_SCRIPT = WORKSPACE / "start_pepper_system_headless.sh"
OPENAI_ENV = WORKSPACE / "config" / "openai.env"

LOG_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

running_process = None
last_start_time = None
last_pepper_ip = ""


def get_host_ip():
    try:
        result = subprocess.run(
            ["bash", "-lc", "ip route get 8.8.8.8 | awk '{for(i=1;i<=NF;i++){if($i==\"src\"){print $(i+1); exit}}}'"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def valid_ip(value):
    pattern = r"^\d{1,3}(\.\d{1,3}){3}$"
    if not re.match(pattern, value):
        return False

    try:
        parts = [int(x) for x in value.split(".")]
        return all(0 <= p <= 255 for p in parts)
    except Exception:
        return False


def stop_existing_processes():
    commands = [
        "pkill -f pepper_full_system.launch.py || true",
        "pkill -f social_skill_manager || true",
        "pkill -f pepper_gesture_node || true",
        "pkill -f pepper_native_wave_node || true",
        "pkill -f pepper_speech_node || true",
        "pkill -f teleop_ps4 || true",
        "pkill -f joy_node || true",
        "pkill -f naoqi_driver || true",
        "pkill -f openai_server || true",
        "pkill -f whisper_transcriber || true",
        "pkill -f pepper_vlm_node || true",
        "pkill -f pepper_dashboard_server || true",
    ]

    subprocess.run(
        ["bash", "-lc", "\n".join(commands)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@app.route("/", methods=["GET"])
def index():
    detected_ip = request.remote_addr or ""

    if detected_ip.startswith("127."):
        detected_ip = ""

    host_ip = get_host_ip()
    dashboard_url = f"http://{host_ip}:5000/" if host_ip else ""

    openai_ok = OPENAI_ENV.exists()

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Pepper Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            margin: 0;
            padding: 30px;
            font-family: Arial, Helvetica, sans-serif;
            background: #f1f5f9;
            color: #0f172a;
        }}
        .box {{
            max-width: 760px;
            margin: auto;
            background: white;
            border-radius: 18px;
            padding: 30px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.12);
        }}
        h1 {{
            font-size: 38px;
            margin-top: 0;
            color: #00af73;
        }}
        label {{
            display: block;
            font-size: 22px;
            margin-top: 22px;
            font-weight: bold;
        }}
        input {{
            width: 100%;
            font-size: 26px;
            padding: 14px;
            margin-top: 10px;
            border: 2px solid #cbd5e1;
            border-radius: 12px;
            box-sizing: border-box;
        }}
        button {{
            width: 100%;
            margin-top: 24px;
            padding: 18px;
            font-size: 26px;
            font-weight: bold;
            border: 0;
            border-radius: 12px;
            background: #00af73;
            color: white;
        }}
        .secondary {{
            background: #334155;
        }}
        .danger {{
            background: #dc2626;
        }}
        .info {{
            font-size: 19px;
            line-height: 1.5;
            background: #e2e8f0;
            padding: 14px;
            border-radius: 12px;
            margin-top: 18px;
        }}
        .warn {{
            color: #b91c1c;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="box">
        <h1>Pepper Setup</h1>

        <div class="info">
            <b>Detected Pepper IP from tablet:</b> {detected_ip or "Not detected"}<br>
            <b>Jetson IP:</b> {host_ip or "Not detected"}<br>
            <b>Dashboard URL:</b> {dashboard_url or "Not available"}<br>
            <b>OpenAI key file:</b> {"OK" if openai_ok else "<span class='warn'>Missing ~/pepper_ws/config/openai.env</span>"}
        </div>

        <form action="/start" method="post">
            <label>Pepper IP</label>
            <input name="pepper_ip" value="{detected_ip}" placeholder="Example: 192.168.0.37" required>

            <button type="submit">Start Pepper System</button>
        </form>

        <form action="/stop" method="post">
            <button class="danger" type="submit">Stop System</button>
        </form>

        <form action="/dashboard" method="get">
            <button class="secondary" type="submit">Open Dashboard</button>
        </form>

        <div class="info">
            After pressing Start, wait about 30–45 seconds. The tablet should switch to the dashboard automatically.
        </div>
    </div>
</body>
</html>
"""
    return html


@app.route("/start", methods=["POST"])
def start():
    global running_process, last_start_time, last_pepper_ip

    pepper_ip = request.form.get("pepper_ip", "").strip()

    if not valid_ip(pepper_ip):
        return f"Invalid Pepper IP: {pepper_ip}", 400

    if not START_SCRIPT.exists():
        return f"Missing start script: {START_SCRIPT}", 500

    host_ip = get_host_ip()

    if not host_ip:
        return "Could not detect Jetson IP.", 500

    stop_existing_processes()

    log_path = LOG_DIR / "setup_server_start.log"

    env = os.environ.copy()
    env["PEPPER_IP"] = pepper_ip
    env["HOST_IP"] = host_ip

    command = ["bash", str(START_SCRIPT)]

    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write("\n\n==============================\n")
    log_file.write(f"START REQUEST {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"PEPPER_IP={pepper_ip}\n")
    log_file.write(f"HOST_IP={host_ip}\n")
    log_file.flush()

    running_process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    last_start_time = time.time()
    last_pepper_ip = pepper_ip

    return redirect("/starting")


@app.route("/starting", methods=["GET"])
def starting():
    host_ip = get_host_ip()
    dashboard_url = f"http://{host_ip}:5000/" if host_ip else "#"

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Starting Pepper</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="35; url={dashboard_url}">
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            background: #f1f5f9;
            padding: 40px;
            color: #0f172a;
            text-align: center;
        }}
        .box {{
            background: white;
            border-radius: 18px;
            padding: 40px;
            max-width: 760px;
            margin: auto;
            box-shadow: 0 8px 20px rgba(0,0,0,0.12);
        }}
        h1 {{
            color: #00af73;
            font-size: 38px;
        }}
        p {{
            font-size: 24px;
        }}
        a {{
            display: block;
            margin-top: 30px;
            font-size: 24px;
            color: #00af73;
        }}
    </style>
</head>
<body>
    <div class="box">
        <h1>Starting Pepper System</h1>
        <p>Please wait 30–45 seconds.</p>
        <p>The tablet will open the dashboard automatically.</p>
        <a href="{dashboard_url}">Open dashboard manually</a>
    </div>
</body>
</html>
"""
    return html


@app.route("/stop", methods=["POST"])
def stop():
    stop_existing_processes()
    return redirect("/")


@app.route("/dashboard", methods=["GET"])
def dashboard():
    host_ip = get_host_ip()
    if not host_ip:
        return "Could not detect Jetson IP.", 500
    return redirect(f"http://{host_ip}:5000/")


@app.route("/status", methods=["GET"])
def status():
    host_ip = get_host_ip()

    return jsonify(
        {
            "jetson_ip": host_ip,
            "last_pepper_ip": last_pepper_ip,
            "last_start_time": last_start_time,
            "running_process_pid": running_process.pid if running_process else None,
        }
    )


def main():
    host_ip = get_host_ip()
    print("Pepper setup server started.")
    print(f"Jetson IP: {host_ip}")
    print("Open on Pepper tablet:")
    print(f"http://{host_ip}:8787/")
    app.run(host="0.0.0.0", port=8787, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
