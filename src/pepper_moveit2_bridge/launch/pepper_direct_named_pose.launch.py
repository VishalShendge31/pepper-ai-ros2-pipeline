from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_config = PathJoinSubstitution([
        FindPackageShare("pepper_moveit2_bridge"),
        "config",
        "pepper_moveit2_bridge.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument("config_file", default_value=default_config),
        DeclareLaunchArgument("allow_real_robot", default_value="false"),
        DeclareLaunchArgument("dry_run", default_value="true"),
        DeclareLaunchArgument("speed", default_value="0.08"),
        DeclareLaunchArgument("goal_topic", default_value="/pepper/moveit_named_goal"),
        DeclareLaunchArgument("joint_command_topic", default_value="/joint_angles"),
        Node(
            package="pepper_moveit2_bridge",
            executable="pepper_direct_named_pose_executor.py",
            name="pepper_direct_named_pose_executor",
            output="screen",
            parameters=[
                LaunchConfiguration("config_file"),
                {
                    "allow_real_robot": LaunchConfiguration("allow_real_robot"),
                    "dry_run": LaunchConfiguration("dry_run"),
                    "speed": LaunchConfiguration("speed"),
                    "goal_topic": LaunchConfiguration("goal_topic"),
                    "joint_command_topic": LaunchConfiguration("joint_command_topic"),
                },
            ],
        ),
    ])
