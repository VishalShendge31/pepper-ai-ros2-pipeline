from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, TimerAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os
import yaml


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def launch_setup(context, *args, **kwargs):
    config_file = LaunchConfiguration("config_file").perform(context)
    urdf_path = LaunchConfiguration("urdf_path").perform(context)

    start_named_planner = LaunchConfiguration("start_named_planner")
    start_executor = LaunchConfiguration("start_executor")
    start_action_saver = LaunchConfiguration("start_action_saver")
    allow_real_robot = LaunchConfiguration("allow_real_robot")
    dry_run = LaunchConfiguration("dry_run")
    planning_group = LaunchConfiguration("planning_group")
    start_neutral_pose = LaunchConfiguration("start_neutral_pose")
    neutral_pose_delay_sec = LaunchConfiguration("neutral_pose_delay_sec")

    moveit_share = get_package_share_directory("pepper_moveit2_config")

    srdf_path = os.path.join(moveit_share, "config", "pepper.srdf")
    kinematics_path = os.path.join(moveit_share, "config", "kinematics.yaml")
    joint_limits_path = os.path.join(moveit_share, "config", "joint_limits.yaml")
    ompl_path = os.path.join(moveit_share, "config", "ompl_planning.yaml")
    controllers_path = os.path.join(moveit_share, "config", "moveit_controllers.yaml")

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

    planning_pipelines_config = {
        "default_planning_pipeline": "ompl",
        "planning_pipelines": ["ompl"],
        "ompl": load_yaml(ompl_path),
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

    return [
        Node(
            condition=IfCondition(start_named_planner),
            package="pepper_moveit2_bridge",
            executable="pepper_named_target_planner",
            name="pepper_named_target_planner",
            output="screen",
            parameters=[
                config_file,
                robot_description,
                robot_description_semantic,
                robot_description_kinematics,
                robot_description_planning,
                planning_pipelines_config,
                trajectory_execution,
                moveit_controllers,
                planning_scene_monitor_parameters,
                {"planning_group": planning_group},
            ],
        ),

        TimerAction(
            period=0.5,
            actions=[
                Node(
                    condition=IfCondition(start_neutral_pose),
                    package="pepper_moveit2_bridge",
                    executable="pepper_publish_neutral_pose.py",
                    name="pepper_neutral_pose_publisher",
                    output="screen",
                    parameters=[
                        config_file,
                        {
                            "allow_real_robot": allow_real_robot,
                            "dry_run": dry_run,
                            "delay_sec": neutral_pose_delay_sec,
                        },
                    ],
                )
            ],
        ),

        Node(
            condition=IfCondition(start_executor),
            package="pepper_moveit2_bridge",
            executable="pepper_trajectory_executor.py",
            name="pepper_trajectory_executor",
            output="screen",
            parameters=[
                config_file,
                {
                    "allow_real_robot": allow_real_robot,
                    "dry_run": dry_run,
                },
            ],
        ),

        Node(
            condition=IfCondition(start_action_saver),
            package="pepper_moveit2_bridge",
            executable="pepper_trajectory_action_saver.py",
            name="pepper_trajectory_action_saver",
            output="screen",
            parameters=[config_file],
        ),
    ]


def generate_launch_description():
    default_config = PathJoinSubstitution([
        FindPackageShare("pepper_moveit2_bridge"),
        "config",
        "pepper_moveit2_bridge.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Bridge parameter YAML file.",
        ),
        DeclareLaunchArgument(
            "urdf_path",
            default_value="/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf",
            description="Absolute path to Pepper URDF file.",
        ),
        DeclareLaunchArgument(
            "start_named_planner",
            default_value="true",
            description="Start C++ MoveIt named-target planner.",
        ),
        DeclareLaunchArgument(
            "start_executor",
            default_value="true",
            description="Start trajectory-to-/joint_angles executor.",
        ),
        DeclareLaunchArgument(
            "start_action_saver",
            default_value="true",
            description="Start trajectory-to-JSON action saver.",
        ),
        DeclareLaunchArgument(
            "allow_real_robot",
            default_value="false",
            description="If true, executor may send commands to the real Pepper.",
        ),
        DeclareLaunchArgument(
            "dry_run",
            default_value="true",
            description="If true, executor logs commands but does not publish to Pepper.",
        ),
        DeclareLaunchArgument(
            "planning_group",
            default_value="right_arm",
            description="MoveIt planning group from Pepper SRDF.",
        ),
        DeclareLaunchArgument(
            "start_neutral_pose",
            default_value="true",
            description="Publish Pepper arms-down neutral pose once before trajectory testing/execution.",
        ),
        DeclareLaunchArgument(
            "neutral_pose_delay_sec",
            default_value="1.0",
            description="Delay before publishing the neutral arms-down pose.",
        ),
        OpaqueFunction(function=launch_setup),
    ])
