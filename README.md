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

### TTS — Two back-ends

**`pepper_speech_node`** (default)
Publishes the LLM response verbatim to `/speech`. NAOqi's `ALTextToSpeech`
renders audio on-robot. Zero latency, robotic voice quality.

**`orpheus_speech_node`** (high-quality)
Runs the Orpheus TTS model with the SNAC (Single-channel Neural Audio Codec) decoder
on the host GPU, generating 24 kHz WAV audio, then streams it over a raw TCP socket
to a listener running on Pepper. This produces near-human voice quality with ~1–3 s
synthesis latency. Requires a GPU and the `snac` + `unsloth` packages.

TCP protocol:
```
connect to PEPPER_IP:12345
→ send uint64 BE (WAV byte length)
→ send WAV bytes
```

---

## Package Structure

```
src/
├── pepper_audio_transcriber/   ASR node (Faster-Whisper + Silero VAD)
├── openai-api-ros2-service/    OpenAI ROS 2 service server + custom interfaces
├── openai_bridge/              Wires /whisper_transcript → GPT → /openai_response
├── pepper_vlm/                 SmolVLM vision node
├── pepper_speech/              NAOqi TTS node + Orpheus TTS node
├── pepper_dashboard/           Flask dashboard server
├── pepper_Ps4/                 PS4 DualShock → /cmd_vel teleop
├── pepper_bringup/             Launch file, config YAML, system monitor
├── naoqi_driver2/              NAOqi ↔ ROS 2 bridge (C++, ament_cmake)
├── naoqi_bridge_msgs/          Custom NAOqi message definitions
├── naoqi_libqi/                Aldebaran libqi C++ library
└── naoqi_libqicore/            Aldebaran libqicore C++ library
```

---

## ROS 2 Topics

| Topic | Type | Description |
|---|---|---|
| `/audio` | `naoqi_bridge_msgs/AudioBuffer` | Raw mic data from Pepper |
| `/camera/front/image_raw` | `sensor_msgs/Image` | Front camera stream |
| `/whisper_transcript` | `std_msgs/String` | ASR output |
| `/openai_response` | `std_msgs/String` | LLM response |
| `/smolvlm/output` | `std_msgs/String` | VLM scene description |
| `/speech` | `std_msgs/String` | Text sent to NAOqi TTS |
| `/cmd_vel` | `geometry_msgs/Twist` | Motion commands |
| `/joy` | `sensor_msgs/Joy` | Raw PS4 input |

---

## Requirements

- Ubuntu 22.04 LTS
- ROS 2 Humble
- Python 3.10
- Pepper robot running NAOqi 2.5.x on the same LAN
- NVIDIA GPU recommended (4 GB+ VRAM for SmolVLM; 8 GB+ for Orpheus TTS)
- OpenAI API key

Python packages: `faster-whisper`, `silero-vad`, `transformers`, `snac`, `unsloth`,
`openai`, `flask`, `soundfile`, `torch`, `opencv-python-headless`, `Pillow`, `numpy`

---

## Installation

### Native (Ubuntu 22.04)

Install ROS 2 Humble following the [official guide](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html), then:

```bash
mkdir -p ~/pepper_ws
cd ~/pepper_ws
git clone https://github.com/VishalShendge31/pepper-ai-ros2-pipeline.git src

# Python dependencies
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip3 install faster-whisper silero-vad soundfile transformers accelerate \
             Pillow opencv-python-headless snac unsloth openai flask flask-cors numpy

# ROS dependencies
sudo rosdep init && rosdep update
rosdep install \
  --from-paths src/naoqi_driver2 src/naoqi_bridge_msgs src/naoqi_libqi src/naoqi_libqicore \
  --ignore-src --rosdistro humble -y

# Build
source /opt/ros/humble/setup.bash
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
```

Set your API key:
```bash
export OPENAI_API_KEY="sk-..."
```

---

### Docker (any machine)

```bash
cp .env.example .env        # fill in OPENAI_API_KEY and PEPPER_IP
./docker_run.sh build       # ~20–40 min first time
./docker_run.sh run         # launches full pipeline
./docker_run.sh shell       # bash inside container for debugging
```

To deploy on a machine without internet access:
```bash
# build machine
docker save pepper-ai-ros2:latest | gzip > pepper-ai-ros2.tar.gz

# target machine
docker load < pepper-ai-ros2.tar.gz
./docker_run.sh run
```

See [DOCKER_README.md](DOCKER_README.md) for GPU configuration, multi-machine ROS 2 DDS setup,
and detailed troubleshooting.

---

## Running

```bash
# Full system
ros2 launch pepper_bringup pepper_full_system.launch.py

# Override Pepper IP
ros2 launch pepper_bringup pepper_full_system.launch.py nao_ip:=192.168.1.50

# Disable VLM (saves ~1 GB VRAM)
ros2 launch pepper_bringup pepper_full_system.launch.py enable_vlm:=false

# Run individual nodes
ros2 run pepper_audio_transcriber whisper_transcriber
ros2 run pepper_vlm pepper_vlm_node
ros2 run pepper_speech orpheus_speech_node
ros2 run pepper_dashboard pepper_dashboard_server
```

Dashboard is accessible at `http://<host-ip>:5000`.

Pepper tablet (SSH into Pepper, run with Python 2.7):
```bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH
python2 ~/open_dashboard.py
```

---

## Configuration

Edit `src/pepper_bringup/config/pepper_system.yaml`:

```yaml
nao_ip: "192.168.100.20"
nao_port: 9559

whisper_model_size: "small"
language: "en"
require_wake_word: true
wake_words: ["hey pepper", "hello pepper", "pepper"]
activation_timeout_sec: 10.0

vlm_model_name: "HuggingFaceTB/SmolVLM-500M-Instruct"
vlm_process_interval_sec: 1.5

tts_backend: "naoqi"          # "naoqi" or "orpheus"
orpheus_tcp_port: 12345

dashboard_port: 5000
```

---

## Troubleshooting

**`ImportError: No module named naoqi`** (on Pepper)
```bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH
```

**`/whisper_transcript` not publishing**
Check `/audio` is flowing: `ros2 topic echo /audio`. If empty, the NAOqi audio module
is not running or the driver is not connected to Pepper. Verify `nao_ip` in the config.

**`/openai_response` not publishing**
Verify `OPENAI_API_KEY` is set in the environment. Check `openai_server` logs for
HTTP 401 (invalid key) or 429 (rate limit).

**SmolVLM out of memory on CPU**
Reduce input resolution in `pepper_vlm_node.py`:
```python
size={"longest_edge": 384}   # default: 768
```
Or launch with `enable_vlm:=false`.

**Dashboard not opening on tablet**
Confirm the host firewall allows port 5000 (`sudo ufw allow 5000`).
Test from Pepper: `wget http://<host-ip>:5000/`.

---

## Maintainer

Vishal Shendge — [vishal.shendge@igcv.fraunhofer.de](mailto:vishal.shendge@igcv.fraunhofer.de)
Fraunhofer IGCV

---

## License

See individual `package.xml` files. Core packages: BSD / Apache-2.0.
