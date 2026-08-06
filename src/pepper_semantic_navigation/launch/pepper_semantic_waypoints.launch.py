from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    waypoints_file = LaunchConfiguration("waypoints_file")

    return LaunchDescription([
        DeclareLaunchArgument(
            "waypoints_file",
            default_value="/home/robot/pepper_ws/maps/pepper_waypoints.yaml",
            description="YAML file where named semantic places are stored",
        ),
        Node(
            package="pepper_semantic_navigation",
            executable="semantic_waypoint_node",
            name="semantic_waypoint_node",
            output="screen",
            parameters=[{
                "map_frame": "map",
                "base_frame": "base_footprint",
                "vlm_topic": "/smolvlm/output",
                "save_place_topic": "/pepper/save_place",
                "go_to_place_topic": "/pepper/go_to_place",
                "status_topic": "/pepper/semantic_status",
                "waypoints_file": waypoints_file,
                "navigate_action": "navigate_to_pose",
            }],
        )
    ])
