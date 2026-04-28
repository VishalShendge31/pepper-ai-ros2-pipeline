# 🐳 Docker Deployment Guide — Pepper AI ROS2 Pipeline

This guide explains how to build, run, and deploy the Pepper AI ROS2 Pipeline
using Docker on **any machine** — no manual ROS 2 installation required.

---

## 📁 Docker File Structure

```
pepper-ai-ros2-pipeline/
├── Dockerfile              ← Main container definition
├── docker-compose.yml      ← Compose-based deployment (recommended)
├── docker_run.sh           ← Convenience shell script
├── .dockerignore           ← Keeps build context lean
├── .env.example            ← Environment variable template
└── docker/
    └── entrypoint.sh       ← Auto-sources ROS 2 + workspace on startup
```

---

## 🧱 What's Inside the Container

| Layer | Contents |
|---|---|
| **Base image** | `ros:humble-ros-base-jammy` (Ubuntu 22.04 LTS) |
| **ROS 2 Humble** | rclpy, rclcpp, cv_bridge, tf2, kdl_parser, image_transport, joy, launch_ros, rosidl, diagnostics |
| **NAOqi stack** | naoqi_libqi, naoqi_libqicore, naoqi_driver2, naoqi_bridge_msgs (built from source) |
| **AI / ML** | PyTorch, faster-whisper, silero-vad, transformers, snac, unsloth, openai |
| **Vision** | OpenCV, Pillow, cv_bridge |
| **Audio** | soundfile, portaudio, pulseaudio |
| **Dashboard** | Flask, flask-cors |
| **System tools** | cmake, boost, libssl, openssh-client, joystick support |
| **Workspace** | All 13 packages built with `colcon build` |

---

## ⚡ Quick Start (Any Machine)

### Prerequisites

- Docker ≥ 24.x installed ([install guide](https://docs.docker.com/engine/install/))
- Docker Compose v2 (`docker compose` — no dash) installed
- *(Optional)* NVIDIA Container Toolkit for GPU support

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/VishalShendge31/pepper-ai-ros2-pipeline.git
cd pepper-ai-ros2-pipeline
```

---

### Step 2 — Set up environment variables

```bash
cp .env.example .env
nano .env   # fill in your values
```

`.env` contents:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
PEPPER_IP=192.168.100.20
PEPPER_USER=nao
ROS_DOMAIN_ID=0
```

> ⚠️ **Never commit your `.env` file.** It is already in `.gitignore`.

---

### Step 3 — Build the Docker image

```bash
# Option A: using the helper script
./docker_run.sh build

# Option B: using Docker Compose
docker compose build

# Option C: using plain Docker
docker build -t pepper-ai-ros2:latest .
```

> ☕ First build takes **20–40 minutes** (downloads ROS, PyTorch, AI models).
> Subsequent builds are fast due to Docker layer caching.

---

### Step 4 — Run the full pipeline

```bash
# Option A: helper script
./docker_run.sh run

# Option B: Docker Compose (recommended — handles all flags automatically)
docker compose up

# Option C: plain Docker
docker run --rm -it \
  --network host \
  -e OPENAI_API_KEY="sk-..." \
  -e PEPPER_IP="192.168.100.20" \
  -p 5000:5000 \
  pepper-ai-ros2:latest
```

This launches:
```
ros2 launch pepper_bringup pepper_full_system.launch.py
```

---

## 🛠️ Helper Script — `docker_run.sh`

```bash
./docker_run.sh build              # Build the Docker image
./docker_run.sh run                # Run the full pipeline
./docker_run.sh shell              # Open a bash shell inside the container
./docker_run.sh launch <args>      # Run with custom launch arguments
```

### Examples

```bash
# Change Pepper's IP at runtime
./docker_run.sh launch nao_ip:=192.168.1.50

# Disable VLM to save resources
./docker_run.sh launch enable_vlm:=false

# Open a shell to debug
./docker_run.sh shell
```

---

## 🖥️ Dashboard

The Flask dashboard runs on **port 5000** and is accessible from the host:

```
http://localhost:5000
```

On a remote machine on the same network:

```
http://<host-machine-ip>:5000
```

---

## 🎮 PS4 Controller Support

The container mounts `/dev/input` for joystick access. To verify it works:

```bash
# Inside the container
ros2 topic echo /joy
```

If empty, run manually:

```bash
ros2 run joy joy_node
```

---

## 🚀 GPU Support (NVIDIA)

To enable GPU acceleration for Whisper, VLM, and LLM:

### 1. Install NVIDIA Container Toolkit on the host

```bash
# Ubuntu
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 2. Swap PyTorch index in `Dockerfile`

Change:
```dockerfile
--index-url https://download.pytorch.org/whl/cpu
```
To:
```dockerfile
--index-url https://download.pytorch.org/whl/cu121
```

### 3. Uncomment GPU block in `docker-compose.yml`

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

### 4. Rebuild

```bash
docker compose build && docker compose up
```

---

## 🌐 ROS 2 Multi-Machine Setup

ROS 2 uses DDS for discovery. Both machines must be on the **same network**.

```bash
# Same ROS_DOMAIN_ID on all machines
export ROS_DOMAIN_ID=0

# On Host PC (inside container) — list active nodes
ros2 node list

# On another machine
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic list    # should see all Pepper topics
```

---

## 📦 Saving and Transferring the Image

### Save the image to a file (for offline/air-gapped deployment)

```bash
docker save pepper-ai-ros2:latest | gzip > pepper-ai-ros2.tar.gz
```

### Load on the target machine

```bash
docker load < pepper-ai-ros2.tar.gz
./docker_run.sh run
```

> Compressed image size: ~8–15 GB depending on PyTorch + model weights.

---

## 🔧 Useful Commands Inside the Container

```bash
# Check all ROS 2 topics
ros2 topic list

# Echo transcript from Whisper
ros2 topic echo /whisper_transcript

# Echo OpenAI responses
ros2 topic echo /openai_response

# Check active nodes
ros2 node list

# Check Pepper camera stream
ros2 topic echo /camera/front/image_raw --no-arr

# Run only the dashboard
ros2 run pepper_dashboard pepper_dashboard_server

# Run only Whisper ASR
ros2 run pepper_audio_transcriber whisper_transcriber
```

---

## 🐛 Troubleshooting

### Container can't reach Pepper

```bash
# Inside container shell
ping 192.168.100.20
```

Ensure both host and Pepper are on the same subnet. Use `--network host` (already set).

---

### `ImportError: No module named naoqi` on Pepper side

This error is on **Pepper's onboard Python 2.7**, not inside the container. Fix on Pepper:

```bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH
```

---

### No `/whisper_transcript` topic

```bash
ros2 topic echo /audio
```

If empty: NAOqi audio driver is not publishing. Verify `naoqi_driver` node is running:

```bash
ros2 node list | grep naoqi
```

---

### No `/openai_response` topic

- Verify `OPENAI_API_KEY` is set: `echo $OPENAI_API_KEY`
- Check OpenAI server logs in the launch output

---

### Dashboard not showing on Pepper tablet

```bash
# From inside the container
ping 192.168.100.20
wget http://$(hostname -I | awk '{print $1}'):5000/
```

If it fails: check firewall and that port 5000 is not blocked.

---

## 🗂️ ROS 2 Nodes Launched

| Component | Node | Function |
|---|---|---|
| NAOqi Driver | `naoqi_driver` | Robot interface |
| ASR | `whisper_transcriber` | Audio → text |
| LLM | `openai_server` | Reasoning |
| Bridge | `transcription_to_openai` | Connect ASR → LLM |
| VLM | `pepper_vlm_node` | Scene understanding |
| TTS | `pepper_speech_node` | Speech output |
| Dashboard | `pepper_dashboard_server` | Visualization |
| Teleop | `joy_node`, `teleop_ps4` | Manual control |

---

## 📌 Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `PEPPER_IP` | `192.168.100.20` | Pepper robot IP address |
| `PEPPER_USER` | `nao` | SSH username on Pepper |
| `ROS_DOMAIN_ID` | `0` | ROS 2 DDS domain |
| `DISPLAY` | `:0` | X11 display (for rviz/GUI) |

---

## 📄 License

BSD / Apache-2.0 — see individual package `package.xml` files.
