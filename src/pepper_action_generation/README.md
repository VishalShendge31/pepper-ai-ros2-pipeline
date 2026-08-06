# Pepper Action Generation

ROS 2 Humble package for generating, visualizing, testing, and saving Pepper robot joint actions using RViz, `joint_state_publisher_gui`, and the real Pepper robot through the NAOqi ROS2 driver.

The package allows:

- Real-time Pepper joint visualization in RViz
- Interactive joint manipulation using sliders
- Live streaming of slider poses to the real Pepper robot
- Saving generated poses as reusable JSON actions
- Creating gesture/action libraries for social interaction systems
- Integration with `pepper_social_skills`

---

# Features

## RViz Pepper Visualization

The package loads the Pepper URDF and visualizes the robot in RViz.

Supported visualization:

- Full Pepper body
- Arm joints
- Head joints
- Hip and knee joints
- Real-time joint updates

---

## Joint Slider GUI

The package uses:

```text
joint_state_publisher_gui
```

to create sliders for every Pepper joint.

This allows manual pose creation without writing joint commands manually.

---

## Real Pepper Joint Streaming

Generated slider values can be streamed directly to the real Pepper robot using:

```text
/joint_angles
```

with:

```text
naoqi_bridge_msgs/msg/JointAnglesWithSpeed
```

The system supports:

- Safe manual pose testing
- Live arm control
- Real-time gesture prototyping

---

## Action Recording

Generated poses can be saved into JSON files for reuse inside:

```text
pepper_social_skills
```

or any other ROS2 gesture system.

---

# Package Structure

```text
pepper_action_generation/
├── config/
├── launch/
│   └── action_generation.launch.py
├── pepper_action_generation/
│   └── action_recorder.py
├── rviz/
│   └── pepper_action_generation.rviz
├── package.xml
├── setup.py
└── README.md
```

---

# Requirements

## ROS2

- ROS 2 Humble

## Required ROS Packages

Install:

```bash
sudo apt update

sudo apt install -y \
  ros-humble-rviz2 \
  ros-humble-joint-state-publisher-gui \
  ros-humble-robot-state-publisher
```

---

# Build

```bash
cd ~/pepper_ws

source /opt/ros/humble/setup.bash

colcon build --symlink-install --packages-select pepper_action_generation

source install/setup.bash
```

---

# Pepper Driver

Start the Pepper NAOqi driver first.

```bash
ros2 launch naoqi_driver naoqi_driver.launch.py nao_ip:=192.168.100.20
```

Wake Pepper:

```bash
ssh nao@192.168.100.20 "qicli call ALMotion.wakeUp"
```

---

# Launch

## Visualization Only

Starts RViz and sliders without moving the real robot.

```bash
ros2 launch pepper_action_generation action_generation.launch.py
```

---

## Real Pepper Streaming

Continuously streams slider movement to the real Pepper robot.

```bash
ros2 launch pepper_action_generation action_generation.launch.py \
  send_to_real_pepper:=true
```

---

# Architecture

```text
joint_state_publisher_gui
            │
            ▼
 /preview_joint_states
            │
            ▼
 robot_state_publisher
            │
            ▼
          RViz

            │
            ▼
      action_recorder
            │
            ▼
       /joint_angles
            │
            ▼
        Real Pepper
```

---

# Topics

## Input Topics

### `/preview_joint_states`

Type:

```text
sensor_msgs/msg/JointState
```

Used for:

- RViz visualization
- Joint recording
- Real Pepper streaming

---

## Output Topics

### `/joint_angles`

Type:

```text
naoqi_bridge_msgs/msg/JointAnglesWithSpeed
```

Used for controlling the real Pepper robot.

---

# Joint Safety

The package uses conservative neutral values at startup:

```text
LShoulderPitch = 1.45
RShoulderPitch = 1.45
```

to keep Pepper arms lowered safely.

Avoid:

- Sudden high-speed movements
- Extreme elbow roll values
- Fast continuous streaming at high speed

Recommended speeds:

```text
0.03 to 0.08
```

---

# Keyboard Controls

Inside the terminal running `action_generation.launch.py`:

## Save Current Pose

```text
s
```

Prompts:

```text
Action name:
Description:
```

The pose is saved into:

```text
~/pepper_ws/src/pepper_social_skills/config/generated_pepper_actions.json
```

---

## Publish Current Pose Once

```text
p
```

Publishes the current slider pose to the real Pepper robot.

---

## Quit

```text
q
```

Stops the recorder node.

---

# Generated Action Format

Saved actions use:

```json
{
  "actions": {
    "example_action": {
      "description": "Example gesture",
      "steps": [
        {
          "joint_names": [
            "RShoulderPitch",
            "RShoulderRoll"
          ],
          "joint_angles": [
            1.0,
            -0.3
          ],
          "speed": 0.05,
          "hold_sec": 1.0
        }
      ]
    }
  }
}
```

---

# Integration with pepper_social_skills

Generated actions can be copied into:

```text
~/pepper_ws/src/pepper_social_skills/config/pepper_actions.json
```

and executed using:

```text
pepper_gesture_node.py
```

This enables:

- Speech gestures
- Social gestures
- Wave gestures
- Interaction gestures
- VLM-triggered gestures

---

# Example Workflow

## Step 1

Launch Pepper driver:

```bash
ros2 launch naoqi_driver naoqi_driver.launch.py nao_ip:=192.168.100.20
```

---

## Step 2

Launch action generation:

```bash
ros2 launch pepper_action_generation action_generation.launch.py \
  send_to_real_pepper:=true
```

---

## Step 3

Move sliders.

Pepper moves in real time.

RViz updates simultaneously.

---

## Step 4

Press:

```text
s
```

to save the pose.

---

## Step 5

Reuse the generated action in:

```text
pepper_social_skills
```

---

# Tested Components

Tested with:

- Pepper robot
- ROS2 Humble
- RViz2
- joint_state_publisher_gui
- NAOqi ROS2 driver
- `/joint_angles`
- `JointAnglesWithSpeed`

---

# Notes

- The package does not use MoveIt.
- The package is intended for gesture generation and social interaction prototyping.
- Full-body balance control is not implemented.
- Use caution while controlling hip and knee joints on the real robot.
- Arm gestures are the safest starting point.

---

# Author

Vishal Shendge

