# Pepper Semantic Autonomous Navigation

This package reconstructs the Pepper navigation stack into two clean modes.

## Mapping mode

`/laser -> /scan_clean -> slam_toolbox -> /map`

## Autonomous navigation mode

saved map + `/scan_clean` localization + Nav2 + semantic waypoints.

## Install

```bash
cd ~/pepper_ws
source /opt/ros/humble/setup.bash

sudo apt update
sudo apt install -y \
  python3-yaml \
  ros-humble-slam-toolbox \
  ros-humble-nav2-bringup \
  ros-humble-nav2-map-server \
  ros-humble-nav2-amcl \
  ros-humble-depthimage-to-laserscan \
  ros-humble-joy

colcon build --packages-select pepper_semantic_navigation --symlink-install
source install/setup.bash
```

## Copy Pepper posture script

```bash
scp ~/pepper_ws/src/pepper_semantic_navigation/scripts/pepper_prepare_posture.py \
  nao@192.168.100.20:~/pepper_prepare_posture.py
```

## Run mapping

```bash
ros2 launch pepper_semantic_navigation pepper_semantic_mapping.launch.py \
  nao_ip:=192.168.100.20 \
  host_ip:=192.168.100.172 \
  enable_vlm:=false \
  enable_dashboard:=false
```

Save map:

```bash
mkdir -p ~/pepper_ws/maps
ros2 run nav2_map_server map_saver_cli -f ~/pepper_ws/maps/pepper_environment
```

## Run autonomous navigation

```bash
ros2 launch pepper_semantic_navigation pepper_autonomous_navigation.launch.py \
  nao_ip:=192.168.100.20 \
  host_ip:=192.168.100.172 \
  map:=/home/robot/pepper_ws/maps/pepper_environment.yaml
```

In RViz, use `2D Pose Estimate`, then send a `Nav2 Goal`.

## Semantic waypoints

```bash
ros2 topic pub --once /pepper/save_place std_msgs/msg/String "{data: 'table'}"
ros2 topic pub --once /pepper/go_to_place std_msgs/msg/String "{data: 'table'}"
ros2 topic echo /pepper/semantic_status
```

## Safety

Only one node should control `/cmd_vel` at a time.

- Mapping: teleop controls `/cmd_vel`.
- Autonomous navigation: Nav2 controls `/cmd_vel`.

Autonomous mode defaults `enable_teleop:=false`.
