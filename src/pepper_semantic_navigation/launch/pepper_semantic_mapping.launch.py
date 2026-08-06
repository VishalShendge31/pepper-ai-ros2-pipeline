from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def as_bool(value: str) -> bool:
    return str(value).lower() in ["true", "1", "yes", "on"]


def add_tablet_action(actions, nao_ip, host_ip, dashboard_port):
    dashboard_url = f"http://{host_ip}:{dashboard_port}/"
    tablet_script = f'''# -*- coding: utf-8 -*-
from naoqi import ALProxy
import time
url = "{dashboard_url}"
tablet = ALProxy("ALTabletService", "127.0.0.1", 9559)
try:
    tablet.enableWebview(True)
except Exception as e:
    print("enableWebview skipped:", e)
try:
    tablet.hideWebview()
    time.sleep(1.0)
except Exception:
    pass
try:
    tablet.loadUrl(url)
    time.sleep(1.0)
    tablet.showWebview()
    print("Opened dashboard:", url)
except Exception as e:
    print("Failed to open dashboard:", e)
'''
    remote_tablet_cmd = (
        "export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH; "
        "export LD_LIBRARY_PATH=/opt/aldebaran/lib:$LD_LIBRARY_PATH; "
        "cat > /tmp/open_dashboard_dynamic.py <<'PY'\\n"
        f"{tablet_script}\\nPY\\npython2 /tmp/open_dashboard_dynamic.py"
    )
    actions.append(TimerAction(period=32.0, actions=[
        ExecuteProcess(cmd=["ssh", f"nao@{nao_ip}", remote_tablet_cmd], output="screen")
    ]))


def launch_setup(context, *args, **kwargs):
    nao_ip = context.launch_configurations["nao_ip"]
    host_ip = context.launch_configurations["host_ip"]
    dashboard_port = context.launch_configurations["dashboard_port"]

    enable_posture_reset = as_bool(context.launch_configurations["enable_posture_reset"])
    enable_driver = as_bool(context.launch_configurations["enable_driver"])
    enable_laser_filter = as_bool(context.launch_configurations["enable_laser_filter"])
    enable_depth_scan = as_bool(context.launch_configurations["enable_depth_scan"])
    enable_slam = as_bool(context.launch_configurations["enable_slam"])
    enable_rviz = as_bool(context.launch_configurations["enable_rviz"])
    enable_teleop = as_bool(context.launch_configurations["enable_teleop"])
    enable_vlm = as_bool(context.launch_configurations["enable_vlm"])
    enable_dashboard = as_bool(context.launch_configurations["enable_dashboard"])
    enable_tablet = as_bool(context.launch_configurations["enable_tablet"])

    actions = []
    pkg_share = get_package_share_directory("pepper_semantic_navigation")
    slam_config = os.path.join(pkg_share, "config", "slam_toolbox_pepper.yaml")
    naoqi_driver_launch = os.path.join(get_package_share_directory("naoqi_driver"), "launch", "naoqi_driver.launch.py")
    pepper_rviz_launch = os.path.join(get_package_share_directory("pepper_navigation"), "launch", "pepper_rviz.launch.py")

    if enable_posture_reset:
        posture_cmd = (
            "export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages:$PYTHONPATH; "
            "export LD_LIBRARY_PATH=/opt/aldebaran/lib:$LD_LIBRARY_PATH; "
            "python2 ~/pepper_prepare_posture.py"
        )
        actions.append(ExecuteProcess(cmd=["ssh", f"nao@{nao_ip}", posture_cmd], output="screen"))

    if enable_driver:
        actions.append(TimerAction(period=6.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(naoqi_driver_launch),
                                     launch_arguments={"nao_ip": nao_ip}.items())
        ]))

    if enable_laser_filter:
        actions.append(TimerAction(period=9.0, actions=[
            Node(package="pepper_semantic_navigation", executable="pepper_laser_filter",
                 name="pepper_laser_filter", output="screen",
                 parameters=[{"input_topic": "/laser", "output_topic": "/scan_clean",
                              "range_min": 0.10, "range_max": 3.00, "use_current_time": True}])
        ]))

    if enable_depth_scan:
        actions.append(TimerAction(period=10.0, actions=[
            Node(package="depthimage_to_laserscan", executable="depthimage_to_laserscan_node",
                 name="depthimage_to_laserscan", output="screen",
                 remappings=[("depth", "/camera/depth/image_raw"),
                             ("depth_camera_info", "/camera/depth/camera_info"),
                             ("scan", "/depth_scan")],
                 parameters=[{"scan_height": 40, "range_min": 0.45, "range_max": 3.00}])
        ]))

    if enable_slam:
        actions.append(TimerAction(period=12.0, actions=[
            Node(package="slam_toolbox", executable="sync_slam_toolbox_node",
                 name="slam_toolbox", output="screen", parameters=[slam_config])
        ]))

    if enable_rviz:
        actions.append(TimerAction(period=15.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(pepper_rviz_launch))
        ]))

    if enable_teleop:
        actions.append(TimerAction(period=18.0, actions=[
            Node(package="joy", executable="joy_node", name="joy_node", output="screen"),
            Node(package="pepper_Ps4", executable="teleop_ps4", name="teleop_ps4", output="screen",
                 parameters=[{"max_linear_x": 0.10, "max_linear_y": 0.06, "max_angular_z": 0.20,
                              "deadzone": 0.22, "invert_linear_x": False,
                              "keep_neck_center_while_moving": True}]),
        ]))

    if enable_vlm:
        actions.append(TimerAction(period=21.0, actions=[
            Node(package="pepper_vlm", executable="pepper_vlm_node", name="pepper_vlm_node",
                 output="screen",
                 parameters=[{"camera_topic": "/camera/front/image_raw",
                              "output_topic": "/smolvlm/output",
                              "process_interval_sec": 2.0}])
        ]))

    if enable_dashboard:
        actions.append(TimerAction(period=24.0, actions=[
            Node(package="pepper_dashboard", executable="pepper_dashboard_server",
                 name="pepper_dashboard_server", output="screen")
        ]))

    if enable_dashboard and enable_tablet:
        add_tablet_action(actions, nao_ip, host_ip, dashboard_port)

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("nao_ip", default_value="192.168.100.20"),
        DeclareLaunchArgument("host_ip", default_value="192.168.100.172"),
        DeclareLaunchArgument("dashboard_port", default_value="5000"),
        DeclareLaunchArgument("enable_posture_reset", default_value="true"),
        DeclareLaunchArgument("enable_driver", default_value="true"),
        DeclareLaunchArgument("enable_laser_filter", default_value="true"),
        DeclareLaunchArgument("enable_depth_scan", default_value="true"),
        DeclareLaunchArgument("enable_slam", default_value="true"),
        DeclareLaunchArgument("enable_rviz", default_value="true"),
        DeclareLaunchArgument("enable_teleop", default_value="true"),
        DeclareLaunchArgument("enable_vlm", default_value="false"),
        DeclareLaunchArgument("enable_dashboard", default_value="false"),
        DeclareLaunchArgument("enable_tablet", default_value="true"),
        OpaqueFunction(function=launch_setup),
    ])
