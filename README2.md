# Pepper Robot AI Pipeline (ROS 2 + Dashboard + Tablet Display)

## Overview

This project implements a real-time multimodal AI pipeline on the Pepper humanoid robot using ROS 2. The system integrates perception, reasoning, and interaction modules into a unified architecture, with a live dashboard displayed on Pepper’s tablet.

### Core Capabilities

- Audio capture and speech recognition (Whisper ASR)
- Large Language Model reasoning (OpenAI)
- Vision-language understanding (VLM)
- Speech synthesis and playback on Pepper
- Real-time dashboard visualization
- Direct tablet rendering without Pepper-side server

---

## System Architecture

### Pepper (Robot Side)

- Publishes sensor data (audio, camera, IMU, etc.)
- Executes motion and speech output
- Displays dashboard via tablet using `ALTabletService`

### Host PC (Computation Side)

- Runs all AI modules (ASR, LLM, VLM)
- Hosts Flask-based dashboard server
- Subscribes to ROS 2 topics
- Sends commands to Pepper tablet

---

## ROS 2 Topics Used

The system relies on the following active topics:

| Topic | Description |
|------|------------|
| `/camera/front/image_raw` | Camera stream |
| `/whisper_transcript` | Speech-to-text output |
| `/openai_response` | LLM-generated response |
| `/smolvlm/output` | Vision-language description |

---

## Prerequisites

- ROS 2 Humble installed
- Pepper robot (NAOqi 2.5.x)
- Python 3 (Host PC)
- Python 2 (Pepper)
- OpenAI API key
- Same network for host and Pepper

---

## Setup

### 1. Source Workspace

```bash
cd ~/pepper_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

## Execution Pipeline

Run each module in a separate terminal.

2. Start NAOqi Driver
```bash
ros2 launch naoqi_driver naoqi_driver.launch.py nao_ip:=192.168.100.20
```
This connects ROS 2 with Pepper hardware.

3. Start Speech-to-Text (Whisper)
```bash
ros2 run pepper_audio_transcriber whisper_transcriber
```
Subscribes to /audio
Publishes /whisper_transcript

4. Start OpenAI Server (LLM)
```bash
ros2 launch openai_server openai_server_launch.py \
  openai_api_key:=<YOUR_API_KEY> \
  openai_model:=gpt-4o-mini
```

5. Bridge Transcript → OpenAI
```bash
ros2 run openai_bridge transcription_to_openai \
  --ros-args -p require_wake_word:=false
```
  
Sends ASR output to LLM
Publishes /openai_response

6. Start Vision-Language Model (VLM)
```bash
source /opt/ros/humble/setup.bash
source ~/pepper_ws/install/setup.bash
ros2 run pepper_vlm pepper_vlm_node
```
Subscribes to camera stream
Publishes /smolvlm/output

7. Start Speech Output (TTS)
```bash
source /opt/ros/humble/setup.bash
source ~/pepper_ws/install/setup.bash
ros2 run pepper_speech pepper_speech_node
```
Converts LLM response into speech
Plays audio on Pepper

8. Start Dashboard Server (Host PC)
```bash
ros2 run pepper_dashboard pepper_dashboard_server
```

Dashboard runs at:

http://192.168.100.172:5000/
Dashboard Features
Live camera stream
Speech transcript (ASR)
Visual scene description (VLM)
LLM reasoning context
Final response output
Robot status display
Tablet Display (No Pepper Server)
Design Change


9. Connect to Pepper
```bash
ssh nao@192.168.100.20
```
Password:
nao

10. Launch Dashboard on Tablet
```bash
python2 ~/open_dashboard.py
```

This script opens:

http://192.168.100.172:5000/

on Pepper’s tablet using ALTabletService.

Network Verification
Check connectivity from Pepper
```bash
ping 192.168.100.172
```
wget -O - http://192.168.100.172:5000/

If these fail:

Pepper cannot reach host PC
Tablet will not display dashboard
Troubleshooting
Issue: Dashboard visible on host but not on tablet

11. Launch pepper PS4 node
```bash
ros2 run joy joy_node
```
```bash
ros2 run pepper_Ps4 teleop_ps4
```
