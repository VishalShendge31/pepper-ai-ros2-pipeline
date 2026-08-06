#!/bin/bash
set -eo pipefail

echo "========================================"
echo "Starting Pepper Full System - stable mode"
echo "========================================"

PEPPER_IP="${PEPPER_IP:-192.168.100.20}"
PEPPER_USER="${PEPPER_USER:-nao}"
HOST_IP="${HOST_IP:-192.168.100.172}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5000}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
OPENAI_KEY="openai-key"
REQUIRE_WAKE_WORD="${REQUIRE_WAKE_WORD:-true}"
WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-auto}"

if [ -z "${OPENAI_KEY}" ] || [ "${OPENAI_KEY}" = "your-openai-key" ] || [ "${OPENAI_KEY}" = "PASTE_YOUR_OPENAI_API_KEY_HERE" ]; then
    echo "ERROR: OPENAI_API_KEY is empty or still a placeholder."
    echo "Run this first:"
    echo "  export OPENAI_API_KEY='your_real_key_here'"
    exit 1
fi

cd ~/pepper_ws || exit 1
source /opt/ros/humble/setup.bash
source install/setup.bash
export OPENAI_API_KEY="${OPENAI_KEY}"

echo "[0] Checking passwordless SSH to Pepper..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "${PEPPER_USER}@${PEPPER_IP}" "echo pepper_ssh_ok" >/tmp/pepper_ssh_check.log 2>&1; then
    echo "ERROR: Passwordless SSH to Pepper is not ready."
    echo "The TTS and animation executor run through non-interactive SSH, so this is required."
    echo "Fix it with:"
    echo "  ssh-copy-id ${PEPPER_USER}@${PEPPER_IP}"
    echo "Then test:"
    echo "  ssh -o BatchMode=yes ${PEPPER_USER}@${PEPPER_IP} 'echo ok'"
    echo "SSH output was:"
    cat /tmp/pepper_ssh_check.log
    exit 1
fi

echo "[1] Validating Pepper action JSON..."
python3 -m json.tool \
    ~/pepper_ws/src/pepper_social_skills/config/pepper_actions.json \
    >/tmp/pepper_actions_check.json

echo "[1b] Validating Pepper NAOqi animation JSON..."
python3 -m json.tool \
    ~/pepper_ws/src/pepper_social_skills/config/pepper_naoqi_animations.json \
    >/tmp/pepper_naoqi_animations_check.json

echo "[2] Stopping old ROS2/Pepper system processes..."
pkill -f pepper_full_system.launch.py || true
pkill -f social_skill_manager || true
pkill -f pepper_gesture_node || true
pkill -f pepper_native_wave_node || true
pkill -f pepper_animation_joystick || true
pkill -f pepper_naoqi_animation_node || true
pkill -f pepper_speech_node || true
pkill -f teleop_ps4 || true
pkill -f joy_node || true
pkill -f naoqi_driver || true
pkill -f openai_server || true
pkill -f transcription_to_openai || true
pkill -f whisper_transcriber || true
pkill -f pepper_vlm_node || true
pkill -f pepper_dashboard_server || true
sleep 2

echo "[3] Launching ROS2 system..."
gnome-terminal -- bash -c "
cd ~/pepper_ws;
source /opt/ros/humble/setup.bash;
source install/setup.bash;
export OPENAI_API_KEY='${OPENAI_KEY}';

ros2 launch pepper_bringup pepper_full_system.launch.py \
  nao_ip:=${PEPPER_IP} \
  robot_user:=${PEPPER_USER} \
  host_ip:=${HOST_IP} \
  dashboard_port:=${DASHBOARD_PORT} \
  enable_naoqi_driver:=true \
  enable_whisper:=true \
  enable_openai_server:=true \
  enable_transcription_bridge:=false \
  enable_vlm:=true \
  enable_tts:=true \
  enable_dashboard:=true \
  enable_teleop:=true \
  enable_system_monitor:=true \
  enable_social_skills:=true \
  enable_gesture_node:=false \
  enable_animation_executor:=true \
  return_to_neutral_after_animation:=true \
  return_to_neutral_after_stop:=true \
  neutral_return_mode:=fixed_joints \
  neutral_speed:=0.25 \
  neutral_hold_sec:=0.5 \
  animation_timeout_sec:=45.0 \
  stop_timeout_sec:=15.0 \
  openai_model:=${OPENAI_MODEL} \
  require_wake_word:=${REQUIRE_WAKE_WORD} \
  whisper_language:=${WHISPER_LANGUAGE};

exec bash
"

echo "[4] Waiting for system startup..."
sleep 35

echo "[5] Waking up Pepper and opening tablet dashboard dynamically..."
ssh -o BatchMode=yes "${PEPPER_USER}@${PEPPER_IP}" \
"export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:\$PYTHONPATH; \
 export LD_LIBRARY_PATH=/opt/aldebaran/lib:\$LD_LIBRARY_PATH; \
 qicli call ALMotion.wakeUp; \
 qicli call ALTextToSpeech.setLanguage German; \
 qicli call ALTextToSpeech.setVolume 0.5; \
 cat > /tmp/open_dashboard_dynamic.py <<'PY'
# -*- coding: utf-8 -*-
from naoqi import ALProxy
import time

url = 'http://${HOST_IP}:${DASHBOARD_PORT}/'
tablet = ALProxy('ALTabletService', '127.0.0.1', 9559)
try:
    tablet.enableWebview(True)
except Exception as e:
    print('enableWebview skipped:', e)
try:
    tablet.hideWebview()
    time.sleep(0.5)
except Exception:
    pass
tablet.loadUrl(url)
time.sleep(1.0)
tablet.showWebview()
print('Opened dashboard:', url)
PY
 python2 /tmp/open_dashboard_dynamic.py"

echo "[6] Basic ROS checks..."
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 node list | grep -E "naoqi|whisper|openai|vlm|speech|dashboard|teleop|social|animation|system_monitor" || true
ros2 topic list | grep -E "whisper_transcript|openai_response|smolvlm|pepper/animation|cmd_vel|joy|camera/front|audio|speech" || true

echo "========================================"
echo "System start command completed."
echo "Dashboard: http://${HOST_IP}:${DASHBOARD_PORT}/"
echo "PS4 buttons: Cross stop all, Square Tanzen, Triangle Elefant, Circle Hey_1, L1 stop Tanzen, R1 stop Elefant."
echo "========================================"
