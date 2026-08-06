# pepper_custom_tts

ROS 2 package for replacing Pepper's built-in NAOqi TTS with a custom Spark-TTS model.

This version uses a normal Python virtual environment. It does **not** require conda.

All Python and AI code runs on the Jetson/host PC. Pepper does not run any custom Python file. Pepper only receives:

1. a generated WAV file copied by `scp`, and
2. a built-in NAOqi command called through `qicli`:

```bash
qicli call ALAudioPlayer.playFile /home/nao/custom_tts_output.wav
```

## Architecture

```text
/openai_response
    ↓
pepper_custom_tts ROS 2 node
    ↓
local Spark-TTS HTTP server
    ↓
Vishalshendge3198/spark_tts_finetune
    ↓
/tmp/pepper_custom_tts/*.wav
    ↓
scp to Pepper
    ↓
qicli call ALAudioPlayer.playFile
    ↓
Pepper speaker
```

## Folder structure

```text
pepper_custom_tts/
├── package.xml
├── setup.py
├── setup.cfg
├── README.md
├── config/
│   ├── pepper_custom_tts.yaml
│   └── spark_tts_server.yaml
├── launch/
│   └── custom_tts.launch.py
├── pepper_custom_tts/
│   ├── __init__.py
│   └── custom_tts_node.py
├── resource/
│   └── pepper_custom_tts
└── scripts/
    ├── install_spark_tts_env.sh
    └── spark_tts_server.py
```

## One-time ROS package build

From your ROS 2 workspace:

```bash
cd ~/pepper_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select pepper_custom_tts --symlink-install
source install/setup.bash
```

## One-time Spark-TTS virtualenv installation

Install OS dependencies first:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git ffmpeg libsndfile1
```

Log in to Hugging Face:

```bash
hf auth login
```

If your system still uses the old command, this also works:

```bash
huggingface-cli login
```

Then install Spark-TTS into a virtual environment:

```bash
bash ~/pepper_ws/src/pepper_custom_tts/scripts/install_spark_tts_env.sh
```

By default this creates:

```text
~/pepper_ws/sparktts_venv
```

and downloads/clones:

```text
~/pepper_ws/custom_tts/Spark-TTS
~/pepper_ws/custom_tts/Spark-TTS-0.5B
~/pepper_ws/custom_tts/spark_tts_finetune
```

## Use your existing venv instead

If you want to install everything inside your current `pepper_venv`, run:

```bash
source ~/pepper_venv/bin/activate
USE_ACTIVE_VENV=1 bash ~/pepper_ws/src/pepper_custom_tts/scripts/install_spark_tts_env.sh
```

Then launch with:

```bash
ros2 launch pepper_custom_tts custom_tts.launch.py \
  venv_python:=$HOME/pepper_venv/bin/python3 \
  robot_ip:=192.168.100.20 \
  robot_user:=nao \
  playback_mode:=pepper_ssh
```

## SSH setup for Pepper

From the Jetson/host PC:

```bash
ssh-copy-id nao@192.168.100.20
ssh nao@192.168.100.20 "qicli call ALMotion.wakeUp"
```

## Run everything with one launch file

Default virtualenv path:

```bash
source /opt/ros/humble/setup.bash
source ~/pepper_ws/install/setup.bash

ros2 launch pepper_custom_tts custom_tts.launch.py \
  robot_ip:=192.168.100.20 \
  robot_user:=nao \
  playback_mode:=pepper_ssh
```

If you installed into `~/pepper_venv`:

```bash
ros2 launch pepper_custom_tts custom_tts.launch.py \
  venv_python:=$HOME/pepper_venv/bin/python3 \
  robot_ip:=192.168.100.20 \
  robot_user:=nao \
  playback_mode:=pepper_ssh
```

## Test

In another terminal:

```bash
source /opt/ros/humble/setup.bash
source ~/pepper_ws/install/setup.bash

ros2 topic pub /openai_response std_msgs/msg/String \
"{data: '[happy] Hallo Vishal, ich spreche jetzt mit deinem feinabgestimmten Spark TTS Modell.'}" \
--once
```

## Useful modes

Generate and play through Pepper:

```bash
playback_mode:=pepper_ssh
```

Generate and play through the Jetson speaker:

```bash
playback_mode:=local
```

Generate only, no playback:

```bash
playback_mode:=none
```

## Important integration note

Disable the old node that publishes or consumes `/speech` for Pepper built-in TTS. This package should subscribe to `/openai_response` directly.
