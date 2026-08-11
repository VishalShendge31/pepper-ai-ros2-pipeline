from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, TimerAction, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


DEFAULT_NAO_IP = os.environ.get("PEPPER_IP", "192.168.100.20")
DEFAULT_HOST_IP = os.environ.get("PEPPER_HOST_IP", os.environ.get("HOST_IP", "192.168.100.172"))
DEFAULT_PEPPER_WS = os.path.expanduser(os.environ.get("PEPPER_WS", "~/pepper_ws"))
DEFAULT_MAP = os.path.join(DEFAULT_PEPPER_WS, "maps", "pepper_environment.yaml")
DEFAULT_WAYPOINTS = os.path.join(DEFAULT_PEPPER_WS, "maps", "pepper_waypoints.yaml")


def as_bool(value: str) -> bool:
    return str(value).lower() in ["true", "1", "yes", "on"]


def launch_setup(context, *args, **kwargs):
    nao_ip = context.launch_configurations["nao_ip"]
    map_file = context.launch_configurations["map"]
    params_file = context.launch_configurations["params_file"]
    waypoints_file = context.launch_configurations["waypoints_file"]

    enable_posture_reset = as_bool(context.launch_configurations["enable_posture_reset"])
    enable_driver = as_bool(context.launch_configurations["enable_driver"])
    enable_laser_filter = as_bool(context.launch_configurations["enable_laser_filter"])
    enable_depth_scan = as_bool(context.launch_configurations["enable_depth_scan"])
    enable_nav2 = as_bool(context.launch_configurations["enable_nav2"])
    enable_rviz = as_bool(context.launch_configurations["enable_rviz"])
    enable_waypoints = as_bool(context.launch_configurations["enable_waypoints"])
    enable_vlm = as_bool(context.launch_configurations["enable_vlm"])
    enable_dashboard = as_bool(context.launch_configurations["enable_dashboard"])
    enable_teleop = as_bool(context.launch_configurations["enable_teleop"])

    actions = []
    if enable_nav2 and enable_teleop:
        actions.append(LogInfo(msg=(
            "WARNING: enable_nav2 and enable_teleop are both true. "
            "Keep only one /cmd_vel source active (prefer enable_teleop:=false for autonomous nav)."
        )))

    nav2_launch = os.path.join(get_package_share_directory("nav2_bringup"), "launch", "bringup_launch.py")
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

    if enable_nav2:
        actions.append(TimerAction(period=13.0, actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                launch_arguments={"map": map_file, "params_file": params_file,
                                  "use_sim_time": "false", "autostart": "true"}.items(),
            )
        ]))

    if enable_waypoints:
        actions.append(TimerAction(period=18.0, actions=[
            Node(package="pepper_semantic_navigation", executable="semantic_waypoint_node",
                 name="semantic_waypoint_node", output="screen",
                 parameters=[{"map_frame": "map", "base_frame": "base_footprint",
                              "vlm_topic": "/smolvlm/output",
                              "save_place_topic": "/pepper/save_place",
                              "go_to_place_topic": "/pepper/go_to_place",
                              "status_topic": "/pepper/semantic_status",
                              "waypoints_file": waypoints_file,
                              "navigate_action": "navigate_to_pose"}])
        ]))

    if enable_rviz:
        actions.append(TimerAction(period=20.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(pepper_rviz_launch))
        ]))

    if enable_vlm:
        actions.append(TimerAction(period=22.0, actions=[
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

    if enable_teleop:
        actions.append(TimerAction(period=26.0, actions=[
            Node(package="joy", executable="joy_node", name="joy_node", output="screen"),
            Node(package="pepper_Ps4", executable="teleop_ps4", name="teleop_ps4", output="screen",
                 parameters=[{"max_linear_x": 0.08, "max_linear_y": 0.04,
                              "max_angular_z": 0.18, "deadzone": 0.22}]),
        ]))

    return actions


def generate_launch_description():
    pkg_share = get_package_share_directory("pepper_semantic_navigation")
    default_params = os.path.join(pkg_share, "config", "nav2_params_pepper.yaml")

    return LaunchDescription([
        DeclareLaunchArgument("nao_ip", default_value=DEFAULT_NAO_IP),
        DeclareLaunchArgument("host_ip", default_value=DEFAULT_HOST_IP),
        DeclareLaunchArgument("dashboard_port", default_value="5000"),
        DeclareLaunchArgument("map", default_value=DEFAULT_MAP),
        DeclareLaunchArgument("waypoints_file", default_value=DEFAULT_WAYPOINTS),
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("enable_posture_reset", default_value="true"),
        DeclareLaunchArgument("enable_driver", default_value="true"),
        DeclareLaunchArgument("enable_laser_filter", default_value="true"),
        DeclareLaunchArgument("enable_depth_scan", default_value="true"),
        DeclareLaunchArgument("enable_nav2", default_value="true"),
        DeclareLaunchArgument("enable_rviz", default_value="true"),
        DeclareLaunchArgument("enable_waypoints", default_value="true"),
        DeclareLaunchArgument("enable_vlm", default_value="true"),
        DeclareLaunchArgument("enable_dashboard", default_value="true"),
        DeclareLaunchArgument("enable_teleop", default_value="false"),
        OpaqueFunction(function=launch_setup),
    ])
