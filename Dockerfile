# ============================================================
# Pepper AI ROS2 Pipeline — Docker Container
# Base: Ubuntu 22.04 + ROS 2 Humble
# Includes: NAOqi driver, Whisper ASR, OpenAI, VLM, TTS, Flask dashboard
# ============================================================

FROM ros:humble-ros-base-jammy

# Prevent interactive apt prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Berlin

# -------------------------------------------------------
# 1. System essentials + build tools
# -------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    cmake \
    git \
    wget \
    curl \
    pkg-config \
    ninja-build \
    # Python
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    python3-numpy \
    # ROS 2 tooling
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    ros-humble-ament-cmake \
    ros-humble-ament-cmake-core \
    # ROS 2 core packages needed by the workspace
    ros-humble-rclpy \
    ros-humble-rclcpp \
    ros-humble-rclcpp-action \
    ros-humble-std-msgs \
    ros-humble-sensor-msgs \
    ros-humble-geometry-msgs \
    ros-humble-action-msgs \
    ros-humble-diagnostic-msgs \
    ros-humble-diagnostic-updater \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    ros-humble-tf2-ros \
    ros-humble-tf2-geometry-msgs \
    ros-humble-tf2-msgs \
    ros-humble-kdl-parser \
    ros-humble-robot-state-publisher \
    ros-humble-launch \
    ros-humble-launch-ros \
    ros-humble-joy \
    ros-humble-rosidl-default-generators \
    ros-humble-rosidl-default-runtime \
    ros-humble-ament-index-cpp \
    # OpenCV + multimedia
    libopencv-dev \
    python3-opencv \
    libsndfile1 \
    libsndfile1-dev \
    portaudio19-dev \
    pulseaudio \
    libasound2-dev \
    # NAOqi / libqi build dependencies
    libboost-all-dev \
    libssl-dev \
    libz-dev \
    # Networking / SSH (for communicating with Pepper)
    openssh-client \
    iputils-ping \
    netcat \
    # Dashboard web server
    # (Flask runs on port 5000)
    # Joystick for PS4 controller
    joystick \
    jstest-gtk \
    # Misc
    gnupg \
    lsb-release \
    ca-certificates \
    software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------
# 2. Python pip packages
# -------------------------------------------------------
RUN pip3 install --upgrade pip setuptools wheel

# AI / ML stack
RUN pip3 install --no-cache-dir \
    torch \
    torchvision \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python packages (GPU-agnostic; swap index above for cu118/cu121 if needed)
RUN pip3 install --no-cache-dir \
    # Speech recognition
    faster-whisper \
    silero-vad \
    soundfile \
    # Vision-Language Model
    transformers \
    accelerate \
    Pillow \
    opencv-python-headless \
    # TTS (Orpheus / SNAC)
    snac \
    # LLM fine-tuning runtime
    unsloth \
    # OpenAI API client
    openai \
    # Web dashboard
    flask \
    flask-cors \
    # ROS 2 Python extras
    pyyaml \
    numpy \
    # Misc utilities
    requests \
    six

# -------------------------------------------------------
# 3. rosdep initialisation (once per image)
# -------------------------------------------------------
RUN rosdep init || true && rosdep update

# -------------------------------------------------------
# 4. Copy workspace source into container
# -------------------------------------------------------
WORKDIR /pepper_ws

COPY src/ ./src/

# -------------------------------------------------------
# 5. Install ROS dependencies via rosdep
# -------------------------------------------------------
RUN . /opt/ros/humble/setup.sh && \
    rosdep install \
        --from-paths src/naoqi_driver2 src/naoqi_bridge_msgs \
                     src/naoqi_libqi src/naoqi_libqicore \
        --ignore-src \
        --rosdistro humble \
        -y || true

# -------------------------------------------------------
# 6. Build the workspace
# -------------------------------------------------------
RUN . /opt/ros/humble/setup.sh && \
    colcon build \
        --symlink-install \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
        --parallel-workers $(nproc) \
        --event-handlers console_cohesion+

# -------------------------------------------------------
# 7. Environment variables baked in
# -------------------------------------------------------
ENV ROS_DISTRO=humble
ENV AMENT_PREFIX_PATH=/pepper_ws/install:/opt/ros/humble
ENV CMAKE_PREFIX_PATH=/pepper_ws/install:/opt/ros/humble
ENV COLCON_PREFIX_PATH=/pepper_ws/install
ENV LD_LIBRARY_PATH=/pepper_ws/install/lib:/opt/ros/humble/lib
ENV PYTHONPATH=/pepper_ws/install/lib/python3.10/site-packages:/opt/ros/humble/lib/python3.10/site-packages
# OpenAI key — override at runtime with: docker run -e OPENAI_API_KEY=sk-...
ENV OPENAI_API_KEY=""
# Pepper robot network settings — override at runtime
ENV PEPPER_IP="192.168.100.20"
ENV PEPPER_USER="nao"

# -------------------------------------------------------
# 8. Copy helper scripts
# -------------------------------------------------------
COPY start_pepper_system.sh /pepper_ws/start_pepper_system.sh
COPY open_dashboard.py      /pepper_ws/open_dashboard.py
RUN chmod +x /pepper_ws/start_pepper_system.sh

# -------------------------------------------------------
# 9. Entrypoint — sources ROS + workspace automatically
# -------------------------------------------------------
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "pepper_bringup", "pepper_full_system.launch.py"]
