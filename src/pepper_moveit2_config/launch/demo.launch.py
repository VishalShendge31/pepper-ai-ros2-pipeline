from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os
import yaml


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}




# Neutral arm-down joint values used by joint_state_publisher_gui.
# Without this, the GUI starts most joints at 0.0, which makes Pepper's
# arms appear in front of the chest in RViz.
NEUTRAL_ARM_DOWN_JOINTS = {
    "HeadYaw": 0.0,
    "HeadPitch": 0.0,
    "LShoulderPitch": 1.55,
    "LShoulderRoll": 0.10,
    "LElbowYaw": -1.55,
    "LElbowRoll": -0.05,
    "LWristYaw": 0.0,
    "RShoulderPitch": 1.55,
    "RShoulderRoll": -0.10,
    "RElbowYaw": 1.55,
    "RElbowRoll": 0.05,
    "RWristYaw": 0.0,
}


def launch_setup(context, *args, **kwargs):
    pkg_share = get_package_share_directory("pepper_moveit2_config")

    urdf_path = LaunchConfiguration("urdf_path").perform(context)
    srdf_path = os.path.join(pkg_share, "config", "pepper.srdf")
    kinematics_path = os.path.join(pkg_share, "config", "kinematics.yaml")
    joint_limits_path = os.path.join(pkg_share, "config", "joint_limits.yaml")
    ompl_path = os.path.join(pkg_share, "config", "ompl_planning.yaml")
    controllers_path = os.path.join(pkg_share, "config", "moveit_controllers.yaml")
    rviz_config = os.path.join(pkg_share, "rviz", "pepper_moveit.rviz")
    move_group_launch = os.path.join(pkg_share, "launch", "move_group.launch.py")

    robot_description = {
        "robot_description": ParameterValue(Command(["cat ", urdf_path]), value_type=str)
    }

    robot_description_semantic = {
        "robot_description_semantic": ParameterValue(Command(["cat ", srdf_path]), value_type=str)
    }

    robot_description_kinematics = {
        "robot_description_kinematics": load_yaml(kinematics_path)
    }

    robot_description_planning = {
        "robot_description_planning": load_yaml(joint_limits_path)
    }

    ompl_config = load_yaml(ompl_path)
    planning_pipelines_config = {
        "default_planning_pipeline": "ompl",
        "planning_pipelines": ["ompl"],
        "ompl": ompl_config,
    }

    trajectory_execution = {
        "moveit_manage_controllers": False,
        "trajectory_execution.allowed_execution_duration_scaling": 1.2,
        "trajectory_execution.allowed_goal_duration_margin": 0.5,
        "trajectory_execution.allowed_start_tolerance": 0.05,
    }

    moveit_controllers = load_yaml(controllers_path)
    moveit_controllers.update({
        "moveit_controller_manager": "moveit_simple_controller_manager/MoveItSimpleControllerManager"
    })

    planning_scene_monitor_parameters = {
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
    }

    robot_state_publisher_node = Node(
        condition=IfCondition(LaunchConfiguration("use_joint_state_gui")),
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[robot_description, {"use_sim_time": False}],
    )

    joint_state_publisher_gui_node = Node(
        condition=IfCondition(LaunchConfiguration("use_joint_state_gui")),
        package="joint_state_publisher_gui",
        executable="joint_state_publisher_gui",
        name="joint_state_publisher_gui",
        output="screen",
        parameters=[robot_description, {"zeros": NEUTRAL_ARM_DOWN_JOINTS}],
    )

    move_group_node = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(move_group_launch),
        launch_arguments={"urdf_path": urdf_path}.items(),
    )

    rviz_node = Node(
        condition=IfCondition(LaunchConfiguration("use_rviz")),
        package="rviz2",
        executable="rviz2",
        name="rviz2_moveit",
        output="screen",
        arguments=["-d", rviz_config],
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            robot_description_planning,
            planning_pipelines_config,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": False},
        ],
    )

    return [
        robot_state_publisher_node,
        joint_state_publisher_gui_node,
        move_group_node,
        rviz_node,
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            "urdf_path",
            default_value="/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf",
            description="Absolute path to Pepper URDF file",
        ),
        DeclareLaunchArgument(
            "use_joint_state_gui",
            default_value="true",
            description="Start joint_state_publisher_gui for offline MoveIt testing",
        ),
        DeclareLaunchArgument(
            "use_rviz",
            default_value="true",
            description="Start RViz with MoveIt MotionPlanning plugin",
        ),
        OpaqueFunction(function=launch_setup),
    ])
