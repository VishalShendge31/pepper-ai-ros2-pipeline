#!/usr/bin/env python3
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy

MSG = """
Pepper PS4 Teleop (teleop_twist_joy style)
-----------------------------------------
Publishes:  /cmd_vel   (geometry_msgs/Twist)
Subscribes: /joy       (sensor_msgs/Joy)

Default mapping (common DS4 on Linux):
  Left stick up/down   -> linear.x    (axis 1, inverted)
  Left stick left/right-> angular.z   (axis 0)
  Hold R1              -> enable (deadman)  (button 5)
  Hold R2              -> turbo (optional)  (button 7, may vary by driver)
  OPTIONS              -> stop (button 9, may vary)

If your buttons/axes differ, change parameters at runtime (shown below).
CTRL-C to quit
"""

def dz(val: float, deadzone: float) -> float:
    return 0.0 if abs(val) < deadzone else val

class TeleopPS4(Node):
    def __init__(self):
        super().__init__('teleop_ps4')
        self.get_logger().info(MSG)

        # --- teleop_twist_joy-like parameters ---
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')

        self.declare_parameter('axis_linear', 1)       # left stick vertical
        self.declare_parameter('axis_angular', 0)      # left stick horizontal
        self.declare_parameter('invert_linear', False)  # DS4 up is often -1
        self.declare_parameter('invert_angular', False)

        self.declare_parameter('scale_linear', 0.25)
        self.declare_parameter('scale_angular', 0.8)

        # Deadman & turbo (set to -1 to disable)
        self.declare_parameter('enable_button', 5)         # R1 typically
        self.declare_parameter('require_enable_button', True)

        self.declare_parameter('turbo_button', 1)         # often R2=7, but varies
        self.declare_parameter('scale_linear_turbo', 0.45)
        self.declare_parameter('scale_angular_turbo', 1.2)

        # Stop button (optional)
        self.declare_parameter('stop_button', -1)          # often OPTIONS=9

        self.declare_parameter('deadzone', 0.05)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('joy_timeout_sec', 0.5)

        topic = self.get_parameter('cmd_vel_topic').value
        self.pub = self.create_publisher(Twist, topic, 10)
        self.sub = self.create_subscription(Joy, 'joy', self.on_joy, 10)

        self.axes = []
        self.buttons = []
        self.last_joy_time = 0.0

        period = 1.0 / float(self.get_parameter('publish_rate_hz').value)
        self.timer = self.create_timer(period, self.loop)

        self.last_log = 0.0

    def on_joy(self, msg: Joy):
        self.axes = list(msg.axes)
        self.buttons = list(msg.buttons)
        self.last_joy_time = time.time()

    def btn(self, idx: int) -> int:
        if idx < 0:  # disabled
            return 0
        return self.buttons[idx] if idx < len(self.buttons) else 0

    def axis(self, idx: int) -> float:
        return self.axes[idx] if idx < len(self.axes) else 0.0

    def loop(self):
        now = time.time()
        timeout = float(self.get_parameter('joy_timeout_sec').value)

        # No recent joystick -> STOP
        if now - self.last_joy_time > timeout:
            self.pub.publish(Twist())
            return

        axis_lin = int(self.get_parameter('axis_linear').value)
        axis_ang = int(self.get_parameter('axis_angular').value)
        inv_lin = bool(self.get_parameter('invert_linear').value)
        inv_ang = bool(self.get_parameter('invert_angular').value)

        deadzone = float(self.get_parameter('deadzone').value)

        enable_button = int(self.get_parameter('enable_button').value)
        require_enable = bool(self.get_parameter('require_enable_button').value)

        turbo_button = int(self.get_parameter('turbo_button').value)
        stop_button = int(self.get_parameter('stop_button').value)

        # Stop button pressed -> STOP immediately
        if stop_button != -1 and self.btn(stop_button) == 1:
            self.pub.publish(Twist())
            return

        enabled = True
        if require_enable and enable_button != -1:
            enabled = (self.btn(enable_button) == 1)

        # Read axes
        lin = self.axis(axis_lin)
        ang = self.axis(axis_ang)

        if inv_lin:
            lin = -lin
        if inv_ang:
            ang = -ang

        lin = dz(lin, deadzone)
        ang = dz(ang, deadzone)

        # Choose normal vs turbo scales
        if turbo_button != -1 and self.btn(turbo_button) == 1:
            s_lin = float(self.get_parameter('scale_linear_turbo').value)
            s_ang = float(self.get_parameter('scale_angular_turbo').value)
            turbo = 1
        else:
            s_lin = float(self.get_parameter('scale_linear').value)
            s_ang = float(self.get_parameter('scale_angular').value)
            turbo = 0

        twist = Twist()
        if enabled:
            twist.linear.x = lin * s_lin
            twist.angular.z = ang * s_ang
        else:
            twist.linear.x = 0.0
            twist.angular.z = 0.0

        self.pub.publish(twist)

        # Log once per second so you can see mapping quickly
        if now - self.last_log > 1.0:
            self.last_log = now
            self.get_logger().info(
                f"axes[{axis_lin}]={lin:.2f} axes[{axis_ang}]={ang:.2f} "
                f"enable(btn {enable_button})={self.btn(enable_button) if enable_button!=-1 else 'NA'} "
                f"turbo={turbo} -> cmd_vel lin.x={twist.linear.x:.2f} ang.z={twist.angular.z:.2f}"
            )

def main():
    rclpy.init()
    node = TeleopPS4()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.pub.publish(Twist())
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

