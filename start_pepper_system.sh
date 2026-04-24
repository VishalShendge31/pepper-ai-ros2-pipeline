#!/bin/bash

echo "========================================"
echo "Starting Pepper Full System"
echo "========================================"

PEPPER_IP="192.168.100.20"
PEPPER_USER="nao"
OPENAI_KEY="${OPENAI_API_KEY}"

cd ~/pepper_ws || exit 1

source /opt/ros/humble/setup.bash
source install/setup.bash

export OPENAI_API_KEY="${OPENAI_KEY}"

echo "[1] Launching ROS2 system..."

gnome-terminal -- bash -c "
cd ~/pepper_ws;
source /opt/ros/humble/setup.bash;
source install/setup.bash;
export OPENAI_API_KEY='${OPENAI_KEY}';
ros2 launch pepper_bringup pepper_full_system.launch.py;
exec bash
"

echo "[2] Waiting 30 seconds for system startup..."
sleep 30

echo "[3] Opening Pepper tablet dashboard..."

ssh ${PEPPER_USER}@${PEPPER_IP} "
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:\$PYTHONPATH
export LD_LIBRARY_PATH=/opt/aldebaran/lib:\$LD_LIBRARY_PATH
python2 ~/open_dashboard.py
"

if [ $? -eq 0 ]; then
    echo "========================================"
    echo "System Started Successfully"
    echo "========================================"
else
    echo "========================================"
    echo "ROS system started, but tablet dashboard failed."
    echo "Check NAOqi Python path on Pepper."
    echo "========================================"
fi
