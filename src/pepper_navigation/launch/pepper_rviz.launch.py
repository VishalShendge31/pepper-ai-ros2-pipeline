from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import Command


def generate_launch_description():
    urdf_path = "/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf"
    rviz_path = "/home/robot/pepper_ws/src/pepper_navigation/rviz/pepper_navigation.rviz"

    return LaunchDescription([
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            parameters=[{
                "robot_description": Command(["cat ", urdf_path]),
                "use_sim_time": False
            }],
            output="screen"
        ),

        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_path],
            output="screen"
        )
    ])
