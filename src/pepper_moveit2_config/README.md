# pepper_moveit2_config

Manual MoveIt 2 configuration package for Pepper / `JulietteY20MP` on ROS 2 Humble.

This package is a workaround for systems where `moveit_setup_assistant` crashes before saving the generated package. It defines SRDF planning groups, named joint states, conservative planning limits, OMPL planning configuration, and launch files for MoveIt 2.

## Why this package exists

On the target Jetson/aarch64 system, MoveIt Setup Assistant loaded the Pepper URDF successfully but crashed with a Qt/RViz segmentation fault before saving `pepper_moveit2_config`. Because the package was never generated, this command fails:

```bash
ros2 launch pepper_moveit2_config demo.launch.py
```

This manual package gives ROS 2 a real `pepper_moveit2_config` package to build and launch.

## Package contents

```text
pepper_moveit2_config/
├── CMakeLists.txt
├── package.xml
├── config/
│   ├── pepper.srdf
│   ├── joint_limits.yaml
│   ├── kinematics.yaml
│   ├── ompl_planning.yaml
│   └── moveit_controllers.yaml
├── launch/
│   ├── demo.launch.py
│   └── move_group.launch.py
└── rviz/
    └── pepper_moveit.rviz
```

## Planning groups

The SRDF defines:

- `right_arm`
- `left_arm`
- `both_arms`
- `head`
- `upper_body`

## Named targets

The starter named targets are:

- `neutral_arms`
- `right_neutral`
- `left_neutral`
- `right_hand_up`
- `right_present`
- `right_wave_start`
- `right_wave_end`
- `left_present`
- `head_forward`

These are conservative starter poses. Always check them in RViz before sending them to real Pepper.

## Install

Copy the folder into your workspace:

```bash
cd ~/pepper_ws/src
unzip /path/to/pepper_moveit2_config_manual.zip
```

Install dependencies:

```bash
sudo apt update
sudo apt install -y \
  ros-humble-moveit \
  ros-humble-moveit-setup-assistant \
  ros-humble-moveit-ros-planning-interface \
  ros-humble-moveit-kinematics \
  ros-humble-moveit-planners-ompl \
  ros-humble-joint-state-publisher-gui
```

Build:

```bash
cd ~/pepper_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select pepper_moveit2_config pepper_moveit2_bridge
source install/setup.bash
```

## Launch planning demo

Offline RViz demo:

```bash
ros2 launch pepper_moveit2_config demo.launch.py \
  urdf_path:=/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf \
  use_joint_state_gui:=true \
  use_rviz:=true
```

Headless MoveIt move_group only:

```bash
ros2 launch pepper_moveit2_config move_group.launch.py \
  urdf_path:=/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf
```

## Use with pepper_moveit2_bridge

Terminal 1:

```bash
ros2 launch pepper_moveit2_config demo.launch.py \
  urdf_path:=/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf \
  use_joint_state_gui:=true \
  use_rviz:=true
```

Terminal 2:

```bash
ros2 launch pepper_moveit2_bridge pepper_moveit2_bridge.launch.py \
  planning_group:=right_arm \
  allow_real_robot:=false \
  dry_run:=true
```

Terminal 3:

```bash
ros2 topic pub --once /pepper/moveit_named_goal std_msgs/msg/String "data: 'right_hand_up'"
```

## Real robot safety

Do not set `dry_run:=false` until:

1. The named state is visually correct in RViz.
2. The planned trajectory is slow and smooth.
3. Pepper is awake and clear of obstacles.
4. Your emergency stop procedure is ready.

Real execution should be done through `pepper_moveit2_bridge`, which converts MoveIt `JointTrajectory` messages into Pepper `/joint_angles` commands.


## v4 alias targets

This version adds alias targets for command-line testing:

- `both_arms_down` for group `both_arms`
- `right_arm_down` for group `right_arm`
- `left_arm_down` for group `left_arm`

These aliases are identical to the neutral arms-down states.

## Neutral arm-down fix

This fixed version prevents Pepper from opening in the zero-joint arm posture, where both hands appear in front of the chest. The neutral/down targets in `config/pepper.srdf` now use a relaxed arm-down pose:

```text
LShoulderPitch:  1.55
LShoulderRoll:   0.10
LElbowYaw:      -1.55
LElbowRoll:     -0.05
LWristYaw:       0.00
RShoulderPitch:  1.55
RShoulderRoll:  -0.10
RElbowYaw:       1.55
RElbowRoll:      0.05
RWristYaw:       0.00
```

The same values are also passed to `joint_state_publisher_gui` through the `zeros` parameter in `launch/demo.launch.py`. This makes RViz start with both arms down instead of forward.

To test the fixed neutral pose:

```bash
cd ~/pepper_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch pepper_moveit2_config demo.launch.py \
  urdf_path:=/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf \
  use_joint_state_gui:=true \
  use_rviz:=true
```

To return Pepper to the neutral arm-down target after a gesture, send:

```bash
ros2 topic pub --once /pepper/moveit_named_goal std_msgs/msg/String "data: 'both_arms_down'"
```
