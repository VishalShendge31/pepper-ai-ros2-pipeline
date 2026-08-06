#!/usr/bin/env python3

import math
import time

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
from std_msgs.msg import String
from naoqi_bridge_msgs.msg import JointAnglesWithSpeed


class PepperPS4Teleop(Node):
    def __init__(self):
        super().__init__("teleop_ps4")

        self.declare_parameter("joy_topic", "/joy")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("joint_angles_topic", "/joint_angles")

        # Keep the original working movement mapping unchanged.
        self.declare_parameter("axis_linear_y", 0)
        self.declare_parameter("axis_linear_x", 1)
        self.declare_parameter("axis_angular_z", 2)

        # OPTIONS button, commonly index 9.
        self.declare_parameter("button_stop", 9)

        # R2 speed boost, commonly button index 7.
        self.declare_parameter("button_speed_boost", 7)
        self.declare_parameter("speed_boost_multiplier", 2.0)

        # Optional R2 axis boost support.
        self.declare_parameter("axis_speed_boost", -1)
        self.declare_parameter("axis_speed_boost_threshold", 0.5)

        # Safe base speeds.
        self.declare_parameter("max_linear_x", 0.12)
        self.declare_parameter("max_linear_y", 0.08)
        self.declare_parameter("max_angular_z", 0.25)

        # Deadzone prevents joystick drift and accidental rotation.
        # Use a stronger default because Pepper must never move from minor PS4 stick noise.
        self.declare_parameter("deadzone", 0.35)
        self.declare_parameter("neutral_calibration_samples", 25)
        self.declare_parameter("movement_activation_frames", 2)
        self.declare_parameter("enable_lateral_motion", True)
        self.declare_parameter("publish_zero_repetitions", 3)
        self.declare_parameter("log_cmd_vel", False)

        # Direction correction.
        self.declare_parameter("invert_linear_x", False)
        self.declare_parameter("invert_linear_y", False)
        self.declare_parameter("invert_angular_z", False)

        # Safety watchdog.
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("joy_timeout_sec", 0.5)

        # Axis neutral calibration.
        self.declare_parameter("use_neutral_calibration", True)

        # Neck center control. Keep enabled unless you intentionally disable it in launch.
        self.declare_parameter("keep_neck_center_while_moving", True)
        self.declare_parameter("neck_yaw_joint", "HeadYaw")
        self.declare_parameter("neck_pitch_joint", "HeadPitch")
        self.declare_parameter("neck_yaw", 0.0)
        self.declare_parameter("neck_pitch", 0.0)
        self.declare_parameter("neck_speed", 0.2)
        self.declare_parameter("neck_publish_rate_hz", 5.0)

        # Behavior/animation button layer.
        # This does not publish /cmd_vel and does not alter movement axes.
        self.declare_parameter("enable_animation_buttons", True)
        self.declare_parameter("animation_command_topic", "/pepper/animation_command")
        self.declare_parameter("animation_button_debounce_sec", 0.35)
        self.declare_parameter("debug_button_edges", True)

        # Default Linux joy mapping for DualShock/PS4 controllers:
        # Cross=0, Circle=1, Triangle=2, Square=3, L1=4, R1=5.
        # Cross=1, Circle=2, Triangle=3, Square=0, L1=4, R1=5.
        # Requested mapping:
        # Cross    -> stop all behaviors
        # Square   -> start demo/Tanzen
        # Triangle -> start demo/Elefant
        # Circle   -> Hey_1
        # L1       -> stop demo/Tanzen
        # R1       -> stop demo/Elefant
        self.declare_parameter("button_stop_all_behaviors", 1)        
        self.declare_parameter("button_hey", 2)                      
        self.declare_parameter("button_elefant", 3)                  
        self.declare_parameter("button_tanzen", 0)                    

        # Specific stop buttons for long-running behaviors.
        self.declare_parameter("button_stop_tanzen", 4)              # L1
        self.declare_parameter("button_stop_elefant", 5)             # R1

        self.declare_parameter("command_stop_all_behaviors", "stop_all_behaviors")
        self.declare_parameter("command_tanzen", "behavior:demo/Tanzen")
        self.declare_parameter("command_elefant", "behavior:demo/Elefant")
        self.declare_parameter("command_stop_tanzen", "stop_behavior:demo/Tanzen")
        self.declare_parameter("command_stop_elefant", "stop_behavior:demo/Elefant")
        self.declare_parameter("command_hey", "animation:Hey_1")

        self.joy_topic = self.get_parameter("joy_topic").value
        self.cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self.joint_angles_topic = self.get_parameter("joint_angles_topic").value

        self.axis_linear_y = int(self.get_parameter("axis_linear_y").value)
        self.axis_linear_x = int(self.get_parameter("axis_linear_x").value)
        self.axis_angular_z = int(self.get_parameter("axis_angular_z").value)

        self.button_stop = int(self.get_parameter("button_stop").value)
        self.button_speed_boost = int(self.get_parameter("button_speed_boost").value)
        self.speed_boost_multiplier = float(self.get_parameter("speed_boost_multiplier").value)

        self.axis_speed_boost = int(self.get_parameter("axis_speed_boost").value)
        self.axis_speed_boost_threshold = float(
            self.get_parameter("axis_speed_boost_threshold").value
        )

        self.max_linear_x = float(self.get_parameter("max_linear_x").value)
        self.max_linear_y = float(self.get_parameter("max_linear_y").value)
        self.max_angular_z = float(self.get_parameter("max_angular_z").value)

        self.deadzone = float(self.get_parameter("deadzone").value)
        self.neutral_calibration_samples = int(
            self.get_parameter("neutral_calibration_samples").value
        )
        self.movement_activation_frames = int(
            self.get_parameter("movement_activation_frames").value
        )
        self.enable_lateral_motion = bool(
            self.get_parameter("enable_lateral_motion").value
        )
        self.publish_zero_repetitions = int(
            self.get_parameter("publish_zero_repetitions").value
        )
        self.log_cmd_vel = bool(self.get_parameter("log_cmd_vel").value)

        self.invert_linear_x = bool(self.get_parameter("invert_linear_x").value)
        self.invert_linear_y = bool(self.get_parameter("invert_linear_y").value)
        self.invert_angular_z = bool(self.get_parameter("invert_angular_z").value)

        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.joy_timeout_sec = float(self.get_parameter("joy_timeout_sec").value)

        self.use_neutral_calibration = bool(
            self.get_parameter("use_neutral_calibration").value
        )

        self.keep_neck_center_while_moving = bool(
            self.get_parameter("keep_neck_center_while_moving").value
        )
        self.neck_yaw_joint = self.get_parameter("neck_yaw_joint").value
        self.neck_pitch_joint = self.get_parameter("neck_pitch_joint").value
        self.neck_yaw = float(self.get_parameter("neck_yaw").value)
        self.neck_pitch = float(self.get_parameter("neck_pitch").value)
        self.neck_speed = float(self.get_parameter("neck_speed").value)
        self.neck_publish_rate_hz = float(
            self.get_parameter("neck_publish_rate_hz").value
        )

        self.enable_animation_buttons = bool(
            self.get_parameter("enable_animation_buttons").value
        )
        self.animation_command_topic = self.get_parameter("animation_command_topic").value
        self.animation_button_debounce_sec = float(
            self.get_parameter("animation_button_debounce_sec").value
        )
        self.debug_button_edges = bool(self.get_parameter("debug_button_edges").value)

        self.animation_button_map = {
            int(self.get_parameter("button_stop_all_behaviors").value): self.get_parameter("command_stop_all_behaviors").value,
            int(self.get_parameter("button_hey").value): self.get_parameter("command_hey").value,
            int(self.get_parameter("button_elefant").value): self.get_parameter("command_elefant").value,
            int(self.get_parameter("button_tanzen").value): self.get_parameter("command_tanzen").value,
            int(self.get_parameter("button_stop_tanzen").value): self.get_parameter("command_stop_tanzen").value,
            int(self.get_parameter("button_stop_elefant").value): self.get_parameter("command_stop_elefant").value,
        }
        self.animation_button_map = {
            k: v for k, v in self.animation_button_map.items() if k >= 0 and str(v).strip()
        }

        self.pub_cmd = self.create_publisher(Twist, self.cmd_vel_topic, 10)

        self.pub_joint_angles = self.create_publisher(
            JointAnglesWithSpeed,
            self.joint_angles_topic,
            10,
        )

        self.pub_animation = self.create_publisher(
            String,
            self.animation_command_topic,
            10,
        )

        self.sub_joy = self.create_subscription(
            Joy,
            self.joy_topic,
            self.joy_callback,
            10,
        )

        self.last_joy_time = 0.0
        self.last_cmd = self.make_zero_cmd()
        self.neutral_axes = None
        self.neutral_axis_samples = []
        self.previous_buttons = None
        self.is_moving = False
        self.active_motion_frames = 0
        self.last_neck_publish_time = 0.0
        self.last_animation_publish_time = 0.0

        timer_period = 1.0 / self.publish_rate_hz
        self.timer = self.create_timer(timer_period, self.publish_cmd_timer)

        self.get_logger().info("")
        self.get_logger().info("Pepper PS4 Teleop started")
        self.get_logger().info("----------------------------------------")
        self.get_logger().info(f"Subscribes: {self.joy_topic}")
        self.get_logger().info(f"Publishes base: {self.cmd_vel_topic}")
        self.get_logger().info(f"Neck topic:     {self.joint_angles_topic}")
        self.get_logger().info(f"Command topic:  {self.animation_command_topic}")
        self.get_logger().info("Left joystick up/down     -> forward/backward")
        self.get_logger().info("Left joystick left/right  -> side movement")
        self.get_logger().info("Right joystick axis       -> rotation")
        self.get_logger().info("Hold R2                   -> 2x speed boost")
        self.get_logger().info("OPTIONS                   -> emergency stop /cmd_vel")
        self.get_logger().info("Cross/X  -> stop_all_behaviors")
        self.get_logger().info("Square   -> behavior:demo/Tanzen")
        self.get_logger().info("Triangle -> behavior:demo/Elefant")
        self.get_logger().info("Circle   -> animation:Hey_1")
        self.get_logger().info(f"Resolved animation button map: {self.animation_button_map}")
        self.get_logger().info("L1       -> stop_behavior:demo/Tanzen")
        self.get_logger().info("R1       -> stop_behavior:demo/Elefant")
        self.get_logger().info(f"axis_linear_x: {self.axis_linear_x}")
        self.get_logger().info(f"axis_linear_y: {self.axis_linear_y}")
        self.get_logger().info(f"axis_angular_z: {self.axis_angular_z}")
        self.get_logger().info(f"deadzone: {self.deadzone}")
        self.get_logger().info(f"neutral calibration: {self.use_neutral_calibration}")
        self.get_logger().info(f"neutral calibration samples: {self.neutral_calibration_samples}")
        self.get_logger().info(f"movement activation frames: {self.movement_activation_frames}")
        self.get_logger().info(f"lateral motion enabled: {self.enable_lateral_motion}")
        self.get_logger().info("Keep joysticks released until calibration is complete.")

    def get_button(self, msg: Joy, index: int) -> bool:
        if index < 0 or index >= len(msg.buttons):
            return False
        return bool(msg.buttons[index])

    def button_pressed_edge(self, msg: Joy, index: int) -> bool:
        if index < 0 or index >= len(msg.buttons):
            return False

        current = bool(msg.buttons[index])

        if self.previous_buttons is None or index >= len(self.previous_buttons):
            return False

        previous = bool(self.previous_buttons[index])
        return current and not previous

    def raw_axis(self, msg: Joy, index: int) -> float:
        if index < 0 or index >= len(msg.axes):
            return 0.0

        value = float(msg.axes[index])

        if not math.isfinite(value):
            return 0.0

        return value

    def corrected_axis(self, msg: Joy, index: int) -> float:
        raw = self.raw_axis(msg, index)

        if (
            self.use_neutral_calibration
            and self.neutral_axes is not None
            and 0 <= index < len(self.neutral_axes)
        ):
            raw = raw - self.neutral_axes[index]

        if abs(raw) < self.deadzone:
            return 0.0

        if raw > 0.0:
            value = (raw - self.deadzone) / (1.0 - self.deadzone)
        else:
            value = (raw + self.deadzone) / (1.0 - self.deadzone)

        return max(-1.0, min(1.0, value))

    def make_zero_cmd(self) -> Twist:
        cmd = Twist()
        cmd.linear.x = 0.0
        cmd.linear.y = 0.0
        cmd.linear.z = 0.0
        cmd.angular.x = 0.0
        cmd.angular.y = 0.0
        cmd.angular.z = 0.0
        return cmd

    def is_speed_boost_pressed(self, msg: Joy) -> bool:
        if self.get_button(msg, self.button_speed_boost):
            return True

        if self.axis_speed_boost >= 0:
            value = self.raw_axis(msg, self.axis_speed_boost)

            if (
                self.use_neutral_calibration
                and self.neutral_axes is not None
                and self.axis_speed_boost < len(self.neutral_axes)
            ):
                value = value - self.neutral_axes[self.axis_speed_boost]

            if abs(value) >= self.axis_speed_boost_threshold:
                return True

        return False

    def publish_animation_buttons(self, msg: Joy):
        if not self.enable_animation_buttons:
            return

        if self.previous_buttons is not None and self.debug_button_edges:
            pressed_edges = []
            max_len = min(len(msg.buttons), len(self.previous_buttons))
            for idx in range(max_len):
                if bool(msg.buttons[idx]) and not bool(self.previous_buttons[idx]):
                    pressed_edges.append(idx)
            if pressed_edges:
                self.get_logger().info(f"Button edge detected: indexes={pressed_edges}, buttons={list(msg.buttons)}")

        now = time.time()
        if now - self.last_animation_publish_time < self.animation_button_debounce_sec:
            return

        for button_index, command in self.animation_button_map.items():
            if self.button_pressed_edge(msg, button_index):
                out = String()
                out.data = str(command)
                self.pub_animation.publish(out)
                self.last_animation_publish_time = now
                self.get_logger().info(
                    f"Behavior/animation button pressed: button={button_index} -> {command}"
                )
                return

    def publish_neck_center(self):
        if not self.keep_neck_center_while_moving:
            return

        now = time.time()
        min_period = 1.0 / max(0.1, self.neck_publish_rate_hz)

        if now - self.last_neck_publish_time < min_period:
            return

        msg = JointAnglesWithSpeed()
        msg.joint_names = [self.neck_yaw_joint, self.neck_pitch_joint]
        msg.joint_angles = [self.neck_yaw, self.neck_pitch]
        msg.speed = self.neck_speed
        msg.relative = False

        self.pub_joint_angles.publish(msg)
        self.last_neck_publish_time = now

    def publish_zero_now(self):
        self.last_cmd = self.make_zero_cmd()
        self.is_moving = False
        self.active_motion_frames = 0

        repetitions = max(1, self.publish_zero_repetitions)
        for _ in range(repetitions):
            self.pub_cmd.publish(self.last_cmd)

    def joy_callback(self, msg: Joy):
        self.last_joy_time = time.time()

        # Robust neutral calibration.
        # Earlier versions used only the first /joy message. That can be unsafe if the
        # stick is slightly touched during startup or the Bluetooth controller reports
        # a noisy first frame. We now average several released-stick frames.
        if self.neutral_axes is None:
            self.previous_buttons = list(msg.buttons)
            self.publish_zero_now()

            if not self.use_neutral_calibration:
                self.neutral_axes = [0.0] * len(msg.axes)
                self.get_logger().info("Joystick neutral calibration disabled; using zero neutral axes.")
                return

            self.neutral_axis_samples.append(list(msg.axes))
            required_samples = max(1, self.neutral_calibration_samples)

            if len(self.neutral_axis_samples) < required_samples:
                if len(self.neutral_axis_samples) in [1, required_samples // 2]:
                    self.get_logger().info(
                        f"Calibrating joystick neutral: "
                        f"{len(self.neutral_axis_samples)}/{required_samples}. "
                        "Keep all sticks released."
                    )
                return

            axis_count = min(len(sample) for sample in self.neutral_axis_samples)
            self.neutral_axes = []

            for axis_index in range(axis_count):
                values = [sample[axis_index] for sample in self.neutral_axis_samples]
                self.neutral_axes.append(sum(values) / float(len(values)))

            self.get_logger().info(f"Joystick neutral calibrated from {required_samples} samples: {self.neutral_axes}")
            self.neutral_axis_samples.clear()
            return

        # Publish behavior/animation commands only on button press edges.
        # This does not affect base velocity calculation.
        self.publish_animation_buttons(msg)

        if self.get_button(msg, self.button_stop):
            self.publish_zero_now()
            self.publish_neck_center()
            self.get_logger().warn("STOP pressed. Published zero /cmd_vel.")
            self.previous_buttons = list(msg.buttons)
            return

        linear_x = self.corrected_axis(msg, self.axis_linear_x)
        linear_y = self.corrected_axis(msg, self.axis_linear_y)
        angular_z = self.corrected_axis(msg, self.axis_angular_z)

        if self.invert_linear_x:
            linear_x *= -1.0

        if self.invert_linear_y:
            linear_y *= -1.0

        if self.invert_angular_z:
            angular_z *= -1.0

        if not self.enable_lateral_motion:
            linear_y = 0.0

        controls_released = (
            abs(linear_x) <= 0.0
            and abs(linear_y) <= 0.0
            and abs(angular_z) <= 0.0
        )

        if controls_released:
            self.publish_zero_now()
            self.previous_buttons = list(msg.buttons)
            return

        self.active_motion_frames += 1
        required_active_frames = max(1, self.movement_activation_frames)

        if self.active_motion_frames < required_active_frames:
            # Reject one-frame spikes from joystick noise.
            self.last_cmd = self.make_zero_cmd()
            self.pub_cmd.publish(self.last_cmd)
            self.previous_buttons = list(msg.buttons)
            return

        speed_scale = 1.0

        if self.is_speed_boost_pressed(msg):
            speed_scale = self.speed_boost_multiplier

        cmd = Twist()
        cmd.linear.x = linear_x * self.max_linear_x * speed_scale
        cmd.linear.y = linear_y * self.max_linear_y * speed_scale
        cmd.linear.z = 0.0

        cmd.angular.x = 0.0
        cmd.angular.y = 0.0
        cmd.angular.z = angular_z * self.max_angular_z * speed_scale

        self.last_cmd = cmd
        self.is_moving = True

        self.pub_cmd.publish(self.last_cmd)

        if self.log_cmd_vel:
            self.get_logger().info(
                f"/cmd_vel linear.x={cmd.linear.x:.3f}, "
                f"linear.y={cmd.linear.y:.3f}, angular.z={cmd.angular.z:.3f}"
            )

        self.publish_neck_center()
        self.previous_buttons = list(msg.buttons)

    def publish_cmd_timer(self):
        now = time.time()

        if (
            self.last_joy_time == 0.0
            or (now - self.last_joy_time) > self.joy_timeout_sec
        ):
            self.publish_zero_now()
            return

        self.pub_cmd.publish(self.last_cmd)

        if self.is_moving:
            self.publish_neck_center()

    def destroy_node(self):
        self.publish_zero_now()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PepperPS4Teleop()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publish_zero_now()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
