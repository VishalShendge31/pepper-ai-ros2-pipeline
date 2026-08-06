from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    slam_config = "/home/robot/pepper_ws/src/pepper_navigation/config/slam_toolbox.yaml"

    return LaunchDescription([
        Node(
            package="slam_toolbox",
            executable="sync_slam_toolbox_node",
            name="slam_toolbox",
            parameters=[slam_config],
            output="screen"
        )
    ])
