from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    slam_config = PathJoinSubstitution([
        FindPackageShare("pepper_navigation"),
        "config",
        "slam_toolbox.yaml",
    ])

    return LaunchDescription([
        Node(
            package="slam_toolbox",
            executable="sync_slam_toolbox_node",
            name="slam_toolbox",
            parameters=[slam_config],
            output="screen"
        )
    ])
