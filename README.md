# Pepper AI Pipeline (ROS 2 Humble)

A real-time multimodal AI system for the **SoftBank Pepper** robot built on **ROS 2 Humble**.
The host PC runs all AI inference; Pepper handles sensing and actuation over the local network via NAOqi.

**Pipeline:** microphone → VAD → ASR → LLM → TTS → Pepper speech
**Parallel:** camera → vision-language model → Flask dashboard → Pepper tablet

---

## Architecture

```
HOST PC
├── pepper_audio_transcriber  Silero VAD + Faster-Whisper → /whisper_transcript
├── openai_bridge             /whisper_transcript → OpenAI GPT → /openai_response
├── pepper_speech             /openai_response → NAOqi /speech  (or Orpheus TCP audio)
├── pepper_vlm                /camera/front/image_raw → SmolVLM-500M → /smolvlm/output
├── pepper_dashboard          Flask :5000 — streams camera, transcript, VLM output
├── pepper_Ps4                joy_node → /cmd_vel teleoperation
└── naoqi_driver2             NAOqi ↔ ROS 2 bridge (C++)

PEPPER ROBOT
├── Publishes  /audio  /camera/front/image_raw
├── Subscribes /speech  /cmd_vel
└── Tablet → WebView → http://<host>:5000
```

---

## Models

### Faster-Whisper (ASR)
Model: `openai/whisper-small` via `faster-whisper` (CTranslate2 backend)

Whisper small runs entirely on the host CPU/GPU with no cloud dependency.
The CTranslate2 runtime gives roughly 4× speedup over the original PyTorch implementation
at identical accuracy, which matters for sub-second transcription latency on a single GPU.

Silero VAD gates Whisper — it processes 512-sample frames at 16 kHz and only triggers
transcription when a complete speech segment is detected (start + end events).
Without VAD, Whisper hallucinates text on silence and wastes compute.

Wake-word logic is layered on top: after detecting one of the configured wake phrases
("Hey Pepper", "Hello Pepper", etc.) the node enters a timed activation window
(default 10 s) and forwards all subsequent speech to the LLM. This prevents
accidental activations from background conversation.

```
Pepper /audio (AudioBuffer)
  ↓ down-mix channels → mono
  ↓ resample to 16 kHz (librosa if needed)
  ↓ Silero VAD — 512-sample frames, threshold=0.5
  ↓ segment collected (speech_start → speech_end or max 20 s)
  ↓ Faster-Whisper.transcribe(beam_size=5, condition_on_previous_text=False)
  ↓ language filter (en / de only)
  ↓ wake-word check → publish /whisper_transcript
```

Key ROS 2 parameters:

| Parameter | Default | Notes |
|---|---|---|
| `model_size` | `small` | `tiny` / `small` / `medium` / `large-v3` |
| `language` | `en` | blank = auto-detect |
| `vad_threshold` | `0.5` | Silero speech probability cutoff |
| `min_silence_duration_ms` | `500` | Gap before segment end is declared |
| `require_wake_word` | `true` | Gate on "Hey Pepper" before forwarding |
| `wake_words` | `["hey pepper"]` | Configurable list |
| `activation_timeout_sec` | `10.0` | Listen window after wake word |
| `max_segment_sec` | `20.0` | Hard cap before forced transcription |

---

### OpenAI GPT (LLM)
Model: configurable via `OPENAI_API_KEY` — gpt-4o, gpt-4, gpt-3.5-turbo

Running a GPT-4-class model locally requires at minimum 80 GB VRAM. The OpenAI API
offloads this cleanly. The `openai_server` node exposes a custom ROS 2 service
(`openai_server_interfaces/OpenaiServer`) so any node in the graph can query the LLM
without knowing the transport details. The `openai_bridge` node wires
`/whisper_transcript` → service call → `/openai_response`.

---

### SmolVLM-500M-Instruct (Vision-Language)
Model: `HuggingFaceTB/SmolVLM-500M-Instruct`

VLMs in the 7B–13B range (LLaVA, InstructBLIP) need 16–24 GB VRAM and take 5–10 s
per image — unusable at Pepper's camera rate. SmolVLM at 500M parameters fits in
roughly 1 GB VRAM (bfloat16) and runs in ~1–2 s per inference on a consumer GPU,
or ~4–6 s on CPU. This makes real-time scene description viable.

The node processes one frame every 1.5 s (configurable). A processing lock prevents
queue pile-up when inference is slower than the topic rate.

```
/camera/front/image_raw (sensor_msgs/Image)
  ↓ cv_bridge → BGR → PIL.Image (RGB)
  ↓ AutoProcessor — resize longest edge to 768 px
  ↓ apply_chat_template + image tokens
  ↓ model.generate(max_new_tokens=80, do_sample=False)
  ↓ decode → strip "Assistant:" prefix
  ↓ publish /smolvlm/output
```

Prompt used at inference:
```
Describe the robot camera image concisely. Mention people, objects, visible
gestures, and emotion. If someone is waving, explicitly say: someone is waving.
```

Device selection is automatic: CUDA if available, otherwise CPU.

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

Vishal Shendge — [shendge.vishal.vilas@gmail.com](mailto:shendge.vishal.vilas@gmail.com)

---

## License

See individual `package.xml` files. Core packages: BSD / Apache-2.0.
