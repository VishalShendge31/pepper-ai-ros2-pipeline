#!/bin/bash
set -e

# Source ROS 2 Humble
source /opt/ros/humble/setup.bash

# Source built workspace (if it exists — i.e. image was built with colcon)
if [ -f /pepper_ws/install/setup.bash ]; then
    source /pepper_ws/install/setup.bash
fi

# Inject runtime environment variables
export OPENAI_API_KEY="${OPENAI_API_KEY}"
export PEPPER_IP="${PEPPER_IP:-192.168.100.20}"
export PEPPER_USER="${PEPPER_USER:-nao}"

echo "========================================"
echo " Pepper AI ROS2 Pipeline Container"
echo "========================================"
echo " ROS_DISTRO  : $ROS_DISTRO"
echo " PEPPER_IP   : $PEPPER_IP"
echo " OPENAI_KEY  : ${OPENAI_API_KEY:0:8}..."
echo "========================================"

exec "$@"
