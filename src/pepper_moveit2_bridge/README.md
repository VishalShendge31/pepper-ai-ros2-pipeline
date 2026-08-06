# pepper_moveit2_bridge

ROS 2 bridge package for using MoveIt 2 with Pepper while keeping the existing NAOqi `/joint_angles` execution interface.

This package does not replace `pepper_social_skills`. It adds a planning layer:

```text
MoveIt 2 named target
  -> planned JointTrajectory
  -> pepper_trajectory_executor
  -> /joint_angles
  -> Pepper
```

It also includes an action saver:

```text
MoveIt 2 planned JointTrajectory
  -> pepper_trajectory_action_saver
  -> generated_moveit_actions.json
  -> pepper_gesture_node can later reuse the saved action
```

## Required second package

You still need a generated MoveIt 2 configuration package, for example:

```text
pepper_moveit2_config
```

Generate that package with MoveIt Setup Assistant using your Pepper URDF:

```text
/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf
```

Recommended planning groups:

- `right_arm`: `RShoulderPitch`, `RShoulderRoll`, `RElbowYaw`, `RElbowRoll`, `RWristYaw`
- `left_arm`: `LShoulderPitch`, `LShoulderRoll`, `LElbowYaw`, `LElbowRoll`, `LWristYaw`
- `both_arms`: all left and right arm joints

Recommended named states:

- `neutral_arms`
- `right_hand_up`
- `right_present`
- `left_present`
- `both_present`
- `right_wave_start`
- `right_wave_end`

## Build

```bash
cd ~/pepper_ws/src
# copy this package here as pepper_moveit2_bridge

cd ~/pepper_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src --rosdistro humble -y
colcon build --symlink-install --packages-select pepper_moveit2_bridge
source install/setup.bash
```

## Run in dry mode first

Start your Pepper driver and MoveIt 2 config first. Then:

```bash
ros2 launch pepper_moveit2_bridge pepper_moveit2_bridge.launch.py \
  planning_group:=right_arm \
  allow_real_robot:=false \
  dry_run:=true
```

Send a named target:

```bash
ros2 topic pub --once /pepper/moveit_named_goal std_msgs/msg/String "data: 'right_hand_up'"
```

The executor will print the planned joint commands without moving the robot.

## Execute on real Pepper

Only after checking the plan in RViz:

```bash
ros2 launch pepper_moveit2_bridge pepper_moveit2_bridge.launch.py \
  planning_group:=right_arm \
  allow_real_robot:=true \
  dry_run:=false
```

Then publish:

```bash
ros2 topic pub --once /pepper/moveit_named_goal std_msgs/msg/String "data: 'right_hand_up'"
```

## Save a planned trajectory as a JSON social action

After a trajectory has been planned:

```bash
ros2 topic pub --once /pepper_moveit/save_action std_msgs/msg/String "data: 'moveit_right_hand_up'"
```

The default output is:

```text
/home/robot/pepper_ws/src/pepper_social_skills/config/generated_moveit_actions.json
```

You can merge selected actions into:

```text
/home/robot/pepper_ws/src/pepper_social_skills/config/pepper_actions.json
```

## Safety rules

- Keep `dry_run:=true` until the planned trajectory is visually checked.
- Start with one arm only.
- Keep `max_velocity_scaling` and `max_acceleration_scaling` low.
- Do not include head, hip, or knee joints in social gestures unless you intentionally design a whole-body motion.
- Do not enable `execute_with_moveit` unless you have a real ros2_control trajectory controller for Pepper.
