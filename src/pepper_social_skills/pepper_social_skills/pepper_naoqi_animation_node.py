#!/usr/bin/env python3

import json
import os
import shlex
import subprocess
import threading
import time
from typing import Optional, Tuple

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


REMOTE_ONESHOT_RUNNER = r'''
# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import sys
import time
import traceback

from naoqi import ALProxy

ROBOT_IP = "127.0.0.1"
ROBOT_PORT = 9559

command_type = os.environ.get("PEPPER_COMMAND_TYPE", "animation").strip()
target = os.environ.get("PEPPER_TARGET", "").strip()
wake_up = os.environ.get("PEPPER_WAKE_UP", "1") == "1"
set_stiffness = os.environ.get("PEPPER_SET_STIFFNESS", "1") == "1"
stand_init_before = os.environ.get("PEPPER_STAND_INIT_BEFORE", "0") == "1"
disable_life = os.environ.get("PEPPER_DISABLE_LIFE", "0") == "1"
return_neutral = os.environ.get("PEPPER_RETURN_NEUTRAL", "1") == "1"
return_neutral_after_stop = os.environ.get("PEPPER_RETURN_NEUTRAL_AFTER_STOP", "1") == "1"
neutral_mode = os.environ.get("PEPPER_NEUTRAL_MODE", "fixed_joints").strip() or "fixed_joints"
neutral_speed = float(os.environ.get("PEPPER_NEUTRAL_SPEED", "0.25"))
neutral_hold_sec = float(os.environ.get("PEPPER_NEUTRAL_HOLD_SEC", "0.5"))
stand_init_speed = float(os.environ.get("PEPPER_STAND_INIT_SPEED", "0.5"))
open_hands_after = os.environ.get("PEPPER_OPEN_HANDS_AFTER", "0") == "1"

NEUTRAL_JOINT_NAMES = [
    "HeadYaw",
    "HeadPitch",
    "LShoulderPitch",
    "LShoulderRoll",
    "LElbowYaw",
    "LElbowRoll",
    "LWristYaw",
    "RShoulderPitch",
    "RShoulderRoll",
    "RElbowYaw",
    "RElbowRoll",
    "RWristYaw",
    "HipRoll",
    "HipPitch",
    "KneePitch",
]

NEUTRAL_JOINT_ANGLES = [
    0.0,
    0.0,
    1.45,
    0.15,
    -1.20,
    -0.50,
    0.0,
    1.45,
    -0.15,
    1.20,
    0.50,
    0.0,
    0.0,
    0.0,
    0.0,
]


def return_fixed_neutral(motion):
    if not return_neutral:
        return

    if neutral_mode.lower() in ["standinit", "stand_init", "posture"]:
        try:
            posture = ALProxy("ALRobotPosture", ROBOT_IP, ROBOT_PORT)
            print("RETURN neutral posture=StandInit speed=%.2f" % stand_init_speed)
            sys.stdout.flush()
            posture.goToPosture("StandInit", stand_init_speed)
            if neutral_hold_sec > 0.0:
                time.sleep(neutral_hold_sec)
            print("DONE return neutral StandInit")
            sys.stdout.flush()
        except Exception as exc:
            print("WARN return neutral StandInit failed: %s" % exc)
            sys.stdout.flush()
    else:
        try:
            print("RETURN fixed neutral joints speed=%.2f joints=%d" % (neutral_speed, len(NEUTRAL_JOINT_NAMES)))
            sys.stdout.flush()
            motion.angleInterpolationWithSpeed(NEUTRAL_JOINT_NAMES, NEUTRAL_JOINT_ANGLES, neutral_speed)
            if open_hands_after:
                try:
                    motion.openHand("LHand")
                    motion.openHand("RHand")
                    print("OK opened hands")
                except Exception as exc:
                    print("WARN open hands failed: %s" % exc)
            if neutral_hold_sec > 0.0:
                time.sleep(neutral_hold_sec)
            print("DONE return fixed neutral joints")
            sys.stdout.flush()
        except Exception as exc:
            print("WARN return fixed neutral joints failed: %s" % exc)
            sys.stdout.flush()


try:
    motion = ALProxy("ALMotion", ROBOT_IP, ROBOT_PORT)
    behavior = ALProxy("ALBehaviorManager", ROBOT_IP, ROBOT_PORT)

    if disable_life:
        try:
            life = ALProxy("ALAutonomousLife", ROBOT_IP, ROBOT_PORT)
            life.setState("disabled")
            print("OK autonomous_life disabled")
        except Exception as exc:
            print("WARN autonomous_life disable failed: %s" % exc)

    if wake_up:
        try:
            motion.wakeUp()
            print("OK wakeUp")
        except Exception as exc:
            print("WARN wakeUp failed: %s" % exc)

    if set_stiffness:
        try:
            motion.setStiffnesses("Body", 1.0)
            print("OK stiffness Body=1.0")
        except Exception as exc:
            print("WARN stiffness failed: %s" % exc)

    if stand_init_before and command_type in ["animation", "behavior"]:
        try:
            posture = ALProxy("ALRobotPosture", ROBOT_IP, ROBOT_PORT)
            posture.goToPosture("StandInit", stand_init_speed)
            print("OK StandInit before command")
        except Exception as exc:
            print("WARN StandInit before command failed: %s" % exc)

    if command_type in ["stop_all", "stop_all_behaviors", "stop"]:
        print("RUN stopAllBehaviors")
        sys.stdout.flush()
        behavior.stopAllBehaviors()
        try:
            motion.stopMove()
            print("OK stopMove")
        except Exception as exc:
            print("WARN stopMove failed: %s" % exc)
        print("DONE stopAllBehaviors")
        sys.stdout.flush()
        if return_neutral_after_stop:
            return_fixed_neutral(motion)
        sys.exit(0)

    if command_type in ["stop_behavior", "stop_behaviour"]:
        if not target:
            print("ERR empty behavior name for stopBehavior")
            sys.exit(2)
        print("RUN stopBehavior %s" % target)
        sys.stdout.flush()
        try:
            behavior.stopBehavior(target)
            print("DONE stopBehavior %s" % target)
        except Exception as exc:
            print("ERR stopBehavior %s failed: %s" % (target, exc))
            sys.exit(1)
        if return_neutral_after_stop:
            return_fixed_neutral(motion)
        sys.exit(0)

    if command_type == "behavior":
        if not target:
            print("ERR empty behavior name")
            sys.exit(2)
        try:
            installed_behaviors = behavior.getInstalledBehaviors()
            print("CHECK behavior installed=%s" % (target in installed_behaviors))
        except Exception as exc:
            print("WARN getInstalledBehaviors failed: %s" % exc)
        print("RUN behavior %s" % target)
        sys.stdout.flush()
        behavior.runBehavior(target)
        print("DONE behavior %s" % target)
        sys.stdout.flush()
        return_fixed_neutral(motion)
        sys.exit(0)

    if command_type == "animation":
        if not target:
            print("ERR empty animation path")
            sys.exit(2)
        anim = ALProxy("ALAnimationPlayer", ROBOT_IP, ROBOT_PORT)
        try:
            installed = anim.getInstalledAnimations()
            print("CHECK animation installed=%s" % (target in installed))
        except Exception as exc:
            print("WARN getInstalledAnimations failed: %s" % exc)
        print("RUN animation %s" % target)
        sys.stdout.flush()
        anim.run(target)
        print("DONE animation %s" % target)
        sys.stdout.flush()
        return_fixed_neutral(motion)
        sys.exit(0)

    print("ERR unknown command_type: %s" % command_type)
    sys.exit(2)

except Exception as exc:
    print("ERR %s target=%s | %s" % (command_type, target, exc))
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)
'''


class PepperNaoqiAnimationNode(Node):
    """
    ROS 2 host-side executor for Pepper NAOqi animations and behaviors.

    Input:
      /pepper/animation_command std_msgs/String

    Supported commands:
      animation:Hey_1
      Hey_1
      animations/Stand/Gestures/Hey_1
      tag:hey
      behavior:demo/Tanzen
      stop_all_behaviors
      stop_behavior:demo/Tanzen
      stop_behavior:demo/Elefant
    """

    def __init__(self):
        super().__init__("pepper_naoqi_animation_node")

        self.declare_parameter("robot_ip", "192.168.100.20")
        self.declare_parameter("robot_user", "nao")
        self.declare_parameter("command_topic", "/pepper/animation_command")
        self.declare_parameter("status_topic", "/pepper/animation_status")
        self.declare_parameter(
            "animations_config",
            os.path.expanduser(
                "~/pepper_ws/src/pepper_social_skills/config/pepper_naoqi_animations.json"
            ),
        )
        self.declare_parameter("ssh_connect_timeout_sec", 5.0)
        self.declare_parameter("animation_timeout_sec", 45.0)
        self.declare_parameter("stop_timeout_sec", 15.0)
        self.declare_parameter("command_cooldown_sec", 0.25)

        self.declare_parameter("wake_up_before_animation", True)
        self.declare_parameter("set_body_stiffness_before_animation", True)
        self.declare_parameter("stand_init_before_animation", False)
        self.declare_parameter("disable_autonomous_life_before_animation", False)

        self.declare_parameter("return_to_neutral_after_animation", True)
        self.declare_parameter("return_to_neutral_after_stop", True)
        self.declare_parameter("neutral_return_mode", "fixed_joints")
        self.declare_parameter("neutral_speed", 0.25)
        self.declare_parameter("neutral_hold_sec", 0.5)
        self.declare_parameter("stand_init_speed", 0.5)
        self.declare_parameter("open_hands_after_animation", False)

        self.declare_parameter("allow_parallel_animations", False)

        self.robot_ip = self.get_parameter("robot_ip").value
        self.robot_user = self.get_parameter("robot_user").value
        self.command_topic = self.get_parameter("command_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.animations_config = os.path.expanduser(self.get_parameter("animations_config").value)
        self.ssh_connect_timeout_sec = float(self.get_parameter("ssh_connect_timeout_sec").value)
        self.animation_timeout_sec = float(self.get_parameter("animation_timeout_sec").value)
        self.stop_timeout_sec = float(self.get_parameter("stop_timeout_sec").value)
        self.command_cooldown_sec = float(self.get_parameter("command_cooldown_sec").value)

        self.wake_up_before_animation = bool(self.get_parameter("wake_up_before_animation").value)
        self.set_body_stiffness_before_animation = bool(
            self.get_parameter("set_body_stiffness_before_animation").value
        )
        self.stand_init_before_animation = bool(self.get_parameter("stand_init_before_animation").value)
        self.disable_autonomous_life_before_animation = bool(
            self.get_parameter("disable_autonomous_life_before_animation").value
        )

        self.return_to_neutral_after_animation = bool(
            self.get_parameter("return_to_neutral_after_animation").value
        )
        self.return_to_neutral_after_stop = bool(
            self.get_parameter("return_to_neutral_after_stop").value
        )
        self.neutral_return_mode = str(self.get_parameter("neutral_return_mode").value)
        self.neutral_speed = float(self.get_parameter("neutral_speed").value)
        self.neutral_hold_sec = float(self.get_parameter("neutral_hold_sec").value)
        self.stand_init_speed = float(self.get_parameter("stand_init_speed").value)
        self.open_hands_after_animation = bool(
            self.get_parameter("open_hands_after_animation").value
        )
        self.allow_parallel_animations = bool(self.get_parameter("allow_parallel_animations").value)

        self.tags, self.animations = self.load_animation_config(self.animations_config)
        self.tag_cycle_index = {tag: 0 for tag in self.tags.keys()}

        self.state_lock = threading.Lock()
        self.last_command_time = 0.0
        self.is_running_animation = False

        self.pub_status = self.create_publisher(String, self.status_topic, 10)
        self.sub_cmd = self.create_subscription(String, self.command_topic, self.command_callback, 10)

        self.get_logger().info("Pepper NAOqi animation/behavior executor started.")
        self.get_logger().info(f"Command topic:         {self.command_topic}")
        self.get_logger().info(f"Status topic:          {self.status_topic}")
        self.get_logger().info(f"Animation config:      {self.animations_config}")
        self.get_logger().info(f"Loaded tags:           {len(self.tags)}")
        self.get_logger().info(f"Loaded animations:     {len(self.animations)}")
        self.get_logger().info(f"Return neutral anim:   {self.return_to_neutral_after_animation}")
        self.get_logger().info(f"Return neutral stop:   {self.return_to_neutral_after_stop}")

    def load_animation_config(self, path: str):
        if not os.path.exists(path):
            raise RuntimeError(f"Animation config does not exist: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tags = data.get("tags", {})
        animations = data.get("animations", {})

        if not isinstance(tags, dict) or not isinstance(animations, dict):
            raise RuntimeError("Invalid animation config. Expected tags and animations dictionaries.")

        return tags, animations

    def publish_status(self, text: str):
        msg = String()
        msg.data = text
        self.pub_status.publish(msg)
        self.get_logger().info(text)

    def resolve_command(self, raw: str) -> Optional[Tuple[str, str, str]]:
        text = raw.strip()
        if not text:
            return None

        if text.startswith("{"):
            try:
                payload = json.loads(text)
                if "command" in payload:
                    text = str(payload["command"]).strip()
                elif "behavior" in payload:
                    text = "behavior:" + str(payload["behavior"]).strip()
                elif "stop_behavior" in payload:
                    text = "stop_behavior:" + str(payload["stop_behavior"]).strip()
                elif "path" in payload:
                    text = str(payload["path"]).strip()
                elif "animation" in payload:
                    text = "animation:" + str(payload["animation"]).strip()
                elif "tag" in payload:
                    text = "tag:" + str(payload["tag"]).strip()
            except Exception:
                pass

        lower = text.lower()

        if lower in ["stop", "stop_all", "stop_all_behaviors", "stopallbehaviors"]:
            return "stop_all", "", "stopAllBehaviors"

        if lower.startswith("stop_behavior:") or lower.startswith("stop_behaviour:"):
            target = text.split(":", 1)[1].strip()
            if not target:
                return None
            return "stop_behavior", target, f"stopBehavior:{target}"

        if lower.startswith("behavior:") or lower.startswith("behaviour:"):
            target = text.split(":", 1)[1].strip()
            if not target:
                return None
            return "behavior", target, f"behavior:{target}"

        if lower.startswith("animation:"):
            name = text.split(":", 1)[1].strip()
            result = self.resolve_animation_name(name)
            if result is None:
                return None
            path, label = result
            return "animation", path, label

        if lower.startswith("tag:"):
            tag = text.split(":", 1)[1].strip()
            result = self.resolve_tag(tag)
            if result is None:
                return None
            path, label = result
            return "animation", path, label

        if text.startswith("animations/"):
            return "animation", text, text

        if text in self.animations:
            result = self.resolve_animation_name(text)
            if result is None:
                return None
            path, label = result
            return "animation", path, label

        for name in self.animations.keys():
            if name.lower() == lower:
                result = self.resolve_animation_name(name)
                if result is None:
                    return None
                path, label = result
                return "animation", path, label

        if text in self.tags:
            result = self.resolve_tag(text)
            if result is None:
                return None
            path, label = result
            return "animation", path, label

        for tag in self.tags.keys():
            if tag.lower() == lower:
                result = self.resolve_tag(tag)
                if result is None:
                    return None
                path, label = result
                return "animation", path, label

        return None

    def resolve_animation_name(self, name: str) -> Optional[Tuple[str, str]]:
        info = self.animations.get(name)
        if not info:
            return None
        path = info.get("path", "")
        if not path:
            return None
        return path, name

    def resolve_tag(self, tag: str) -> Optional[Tuple[str, str]]:
        candidates = self.tags.get(tag, [])
        candidates = [name for name in candidates if name in self.animations]
        if not candidates:
            return None

        index = self.tag_cycle_index.get(tag, 0) % len(candidates)
        self.tag_cycle_index[tag] = index + 1
        name = candidates[index]

        result = self.resolve_animation_name(name)
        if result is None:
            return None

        path, _ = result
        return path, f"tag:{tag}->{name}"

    def is_stop_command_type(self, command_type: str) -> bool:
        return command_type in ["stop_all", "stop_behavior"]

    def command_callback(self, msg: String):
        resolved = self.resolve_command(msg.data)

        if resolved is None:
            self.publish_status(f"UNKNOWN animation/behavior command: {msg.data}")
            return

        command_type, target, label = resolved
        now = time.time()

        with self.state_lock:
            # Stop commands must bypass cooldown and busy-state blocking.
            if not self.is_stop_command_type(command_type):
                if now - self.last_command_time < self.command_cooldown_sec:
                    return
                self.last_command_time = now

                if self.is_running_animation and not self.allow_parallel_animations:
                    self.publish_status("BUSY: animation/behavior still running; command ignored.")
                    return

        thread = threading.Thread(
            target=self.execute_command_thread,
            args=(command_type, target, label),
            daemon=True,
        )
        thread.start()

    def build_remote_command(self, command_type: str, target: str) -> str:
        wake = "1" if self.wake_up_before_animation else "0"
        stiffness = "1" if self.set_body_stiffness_before_animation else "0"
        stand_init_before = "1" if self.stand_init_before_animation else "0"
        disable_life = "1" if self.disable_autonomous_life_before_animation else "0"
        return_neutral = "1" if self.return_to_neutral_after_animation else "0"
        return_neutral_after_stop = "1" if self.return_to_neutral_after_stop else "0"
        neutral_mode = shlex.quote(self.neutral_return_mode)
        neutral_speed = shlex.quote(str(self.neutral_speed))
        neutral_hold_sec = shlex.quote(str(self.neutral_hold_sec))
        stand_init_speed = shlex.quote(str(self.stand_init_speed))
        open_hands_after = "1" if self.open_hands_after_animation else "0"

        return (
            "cat > /tmp/pepper_animation_behavior_once.py <<'PY'\n"
            + REMOTE_ONESHOT_RUNNER
            + "\nPY\n"
            + "export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH; "
            + "export LD_LIBRARY_PATH=/opt/aldebaran/lib:$LD_LIBRARY_PATH; "
            + f"PEPPER_COMMAND_TYPE={shlex.quote(command_type)} "
            + f"PEPPER_TARGET={shlex.quote(target)} "
            + f"PEPPER_WAKE_UP={wake} "
            + f"PEPPER_SET_STIFFNESS={stiffness} "
            + f"PEPPER_STAND_INIT_BEFORE={stand_init_before} "
            + f"PEPPER_DISABLE_LIFE={disable_life} "
            + f"PEPPER_RETURN_NEUTRAL={return_neutral} "
            + f"PEPPER_RETURN_NEUTRAL_AFTER_STOP={return_neutral_after_stop} "
            + f"PEPPER_NEUTRAL_MODE={neutral_mode} "
            + f"PEPPER_NEUTRAL_SPEED={neutral_speed} "
            + f"PEPPER_NEUTRAL_HOLD_SEC={neutral_hold_sec} "
            + f"PEPPER_STAND_INIT_SPEED={stand_init_speed} "
            + f"PEPPER_OPEN_HANDS_AFTER={open_hands_after} "
            + "python2 -u /tmp/pepper_animation_behavior_once.py"
        )

    def execute_command_thread(self, command_type: str, target: str, label: str):
        is_stop = self.is_stop_command_type(command_type)

        if not is_stop:
            with self.state_lock:
                self.is_running_animation = True

        self.publish_status(f"START {command_type}: {label} | {target}")

        remote = f"{self.robot_user}@{self.robot_ip}"
        timeout = self.stop_timeout_sec if is_stop else self.animation_timeout_sec
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={int(self.ssh_connect_timeout_sec)}",
            remote,
            self.build_remote_command(command_type, target),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )

            output = (result.stdout or "").strip()
            if output:
                for line in output.splitlines():
                    self.publish_status(f"REMOTE: {line.strip()}")

            if result.returncode == 0:
                self.publish_status(f"SUCCESS {command_type}: {label}")
            else:
                self.publish_status(
                    f"ERROR {command_type} failed: {label} | returncode={result.returncode}"
                )

        except subprocess.TimeoutExpired:
            self.publish_status(f"ERROR {command_type} timeout after {timeout:.1f}s: {label}")
        except Exception as exc:
            self.publish_status(f"ERROR {command_type} execution failed: {label} | {exc}")
        finally:
            if not is_stop:
                with self.state_lock:
                    self.is_running_animation = False

    def destroy_node(self):
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PepperNaoqiAnimationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
