#!/bin/bash
set -u
source /opt/ros/humble/setup.bash
source ~/pepper_ws/install/setup.bash

echo "================ Pepper ROS health check ================"
echo "Nodes:"
ros2 node list | sort

echo ""
echo "Required topics present:"
for topic in \
  /audio \
  /camera/front/image_raw \
  /whisper_transcript \
  /openai_response \
  /smolvlm/output \
  /speech \
  /cmd_vel \
  /joy \
  /pepper/animation_command \
  /pepper/animation_status \
  /social_skill/state \
  /social_skill/event \
  /social_skill/active_skill; do
    if ros2 topic list | grep -qx "$topic"; then
        echo "OK      $topic"
    else
        echo "MISSING $topic"
    fi
done

echo ""
echo "Publisher/subscriber wiring:"
for topic in /whisper_transcript /openai_response /smolvlm/output /pepper/animation_command /pepper/animation_status /cmd_vel /joy; do
    echo "---- $topic"
    ros2 topic info -v "$topic" 2>/dev/null | sed -n '1,18p' || true
done

echo ""
echo "Useful live tests:"
echo "  ros2 topic pub --once /pepper/animation_command std_msgs/msg/String \"{data: 'animation:Hey_1'}\""
echo "  ros2 topic pub --once /pepper/animation_command std_msgs/msg/String \"{data: 'behavior:demo/Tanzen'}\""
echo "  ros2 topic pub --once /pepper/animation_command std_msgs/msg/String \"{data: 'stop_behavior:demo/Tanzen'}\""
echo "  ros2 topic pub --once /openai_response std_msgs/msg/String \"{data: 'Hallo, ich bin Pepper.'}\""
