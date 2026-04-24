Below is a complete, technically rigorous README for your full system. It consolidates the bringup package, all dependent modules, runtime orchestration, and Pepper-side execution into a reproducible workflow.

---

# Pepper AI System (ROS 2 Full Pipeline)

## 1. Overview

This repository implements a **real-time multimodal AI pipeline on Pepper** using ROS 2. The system integrates:

* Speech recognition (Whisper ASR)
* Language reasoning (OpenAI LLM)
* Vision-language perception (VLM)
* Speech synthesis (TTS on Pepper)
* Teleoperation (PS4 controller)
* Live dashboard visualization (Flask → Pepper Tablet)

The architecture follows a **distributed design**:

* Pepper handles sensing, actuation, and tablet display
* Host PC performs all AI computation

Core data flow:

```
Audio → ASR → LLM → TTS → Pepper Speech
Camera → VLM → Dashboard
```

Key ROS topics include `/whisper_transcript`, `/openai_response`, `/smolvlm/output`, and `/camera/front/image_raw`, which form the backbone of the pipeline. 

---

## 2. System Architecture

### 2.1 Robot Side (Pepper)

* NAOqi runtime (2.5.x)
* Sensor publishers:

  * `/audio`
  * `/camera/front/image_raw`
* Actuators:

  * `/cmd_vel` (motion)
  * `/speech` (audio output)
* Tablet rendering via `ALTabletService`

---

### 2.2 Host PC (ROS 2 + AI Stack)

* ROS 2 Humble
* Whisper ASR node
* OpenAI LLM server
* ASR → LLM bridge
* Vision-language model
* TTS interface
* Flask dashboard server
* PS4 teleoperation nodes

---

## 3. Package Structure

```
pepper_ws/
├── src/
│   ├── pepper_bringup/
│   │   ├── launch/
│   │   │   └── pepper_full_system.launch.py
│   │   ├── config/
│   │   │   └── pepper_system.yaml
│   │   ├── pepper_bringup/
│   │   │   └── system_monitor.py
│   │   ├── scripts/
│   │   │   └── open_pepper_tablet.sh
│   │   ├── package.xml
│   │   ├── setup.py
│   │   └── README.md
│   ├── pepper_audio_transcriber/
│   ├── openai_server/
│   ├── openai_bridge/
│   ├── pepper_vlm/
│   ├── pepper_speech/
│   ├── pepper_dashboard/
│   └── pepper_Ps4/
```

---

## 4. Prerequisites

### Hardware

* Pepper Robot (NAOqi 2.5.x)
* Host PC with GPU (recommended for Whisper/VLM)

### Software

* Ubuntu 22.04
* ROS 2 Humble
* Python 3 (host)
* Python 2.7 (Pepper)
* OpenAI API Key

### Network

* Pepper and host must be on the same network

---

## 5. Installation

### 5.1 Clone Workspace

```bash
cd ~
mkdir -p pepper_ws/src
cd pepper_ws/src

# clone your repositories here
```

---

### 5.2 Build Workspace

```bash
cd ~/pepper_ws

source /opt/ros/humble/setup.bash
colcon build --symlink-install

source install/setup.bash
```

---

## 6. Environment Setup

### OpenAI API Key

```bash
export OPENAI_API_KEY="your_api_key_here"
```

To persist:

```bash
echo 'export OPENAI_API_KEY="your_api_key_here"' >> ~/.bashrc
```

---

## 7. Running the System

### Option 1: Manual Launch

```bash
ros2 launch pepper_bringup pepper_full_system.launch.py
```

---

### Option 2: Automated Script (Recommended)

```bash
~/pepper_ws/start_pepper_system.sh
```

This script performs:

1. ROS2 system launch
2. Wait for initialization
3. SSH into Pepper
4. Start tablet dashboard

---

## 8. Pepper Tablet Dashboard

### Automatic Execution

The script runs:

```bash
python2 ~/open_dashboard.py
```

on Pepper.

### Important Requirement

Pepper must have NAOqi Python path configured:

```bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH
```

If not set, you will get:

```
ImportError: No module named naoqi
```

---

## 9. ROS 2 Nodes and Roles

| Component    | Node                      | Function            |
| ------------ | ------------------------- | ------------------- |
| NAOqi Driver | `naoqi_driver`            | Robot interface     |
| ASR          | `whisper_transcriber`     | Audio → text        |
| LLM          | `openai_server`           | Reasoning           |
| Bridge       | `transcription_to_openai` | Connect ASR → LLM   |
| VLM          | `pepper_vlm_node`         | Scene understanding |
| TTS          | `pepper_speech_node`      | Speech output       |
| Dashboard    | `pepper_dashboard_server` | Visualization       |
| Teleop       | `joy_node`, `teleop_ps4`  | Manual control      |

---

## 10. Key ROS Topics

| Topic                     | Description            |
| ------------------------- | ---------------------- |
| `/audio`                  | Microphone input       |
| `/camera/front/image_raw` | Camera stream          |
| `/whisper_transcript`     | ASR output             |
| `/openai_response`        | LLM output             |
| `/smolvlm/output`         | Vision-language output |
| `/speech`                 | TTS output             |
| `/cmd_vel`                | Motion control         |

These topics were verified during runtime and are actively used across the pipeline. 

---

## 11. System Monitor

The bringup package includes:

```
pepper_bringup/system_monitor.py
```

Function:

* Periodically checks required topics
* Logs missing components
* Ensures pipeline integrity

---

## 12. Troubleshooting

### 12.1 NAOqi Import Error

```
ImportError: No module named naoqi
```

Fix:

```bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH
```

---

### 12.2 Dashboard Not Showing on Tablet

Check:

```bash
ping <host_ip>
wget http://<host_ip>:5000/
```

If failing:

* Network misconfiguration
* Firewall blocking port 5000

---

### 12.3 No `/whisper_transcript`

Check:

```bash
ros2 topic echo /audio
```

If empty:

* Audio driver not publishing
* NAOqi audio disabled

---

### 12.4 No `/openai_response`

* Verify API key
* Check OpenAI server logs

---

### 12.5 Teleop Not Working

```bash
ros2 topic echo /joy
```

If empty:

```bash
ros2 run joy joy_node
```

---

## 13. Advanced Usage

### Disable Components

```bash
ros2 launch pepper_bringup pepper_full_system.launch.py enable_vlm:=false
```

---

### Change Pepper IP

```bash
ros2 launch pepper_bringup pepper_full_system.launch.py nao_ip:=192.168.1.10
```

---

### Run Only Dashboard

```bash
ros2 run pepper_dashboard pepper_dashboard_server
```

---

## 14. Design Decisions

### Centralized AI Processing

All heavy models run on host:

* reduces Pepper CPU load
* enables GPU acceleration

### ROS 2 Topic-Based Decoupling

Each module communicates via topics:

* modular design
* easy debugging
* scalable architecture

### Delayed Launch (TimerAction)

Prevents race conditions:

* ensures `/audio` exists before ASR
* ensures `/openai_response` before TTS

---

## 15. Future Improvements

* Lifecycle nodes (managed startup/shutdown)
* Health monitoring dashboard
* Automatic recovery on node failure
* Topic synchronization (message_filters)
* Replace sleep with readiness checks
* Containerization (Docker)

---

## 16. Summary

This system provides:

* End-to-end humanoid AI pipeline
* Real-time multimodal perception and interaction
* Scalable ROS 2 architecture
* Fully automated deployment via launch + bash orchestration

It transforms Pepper into an interactive AI agent integrating speech, vision, reasoning, and action within a unified ROS 2 framework.

---

