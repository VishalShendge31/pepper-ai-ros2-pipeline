from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    urdf_path = LaunchConfiguration("urdf_path")
    rviz_config = LaunchConfiguration("rviz_config")
    send_to_real_pepper = LaunchConfiguration("send_to_real_pepper")

    robot_description = ParameterValue(
        Command(["cat ", urdf_path]),
        value_type=str
    )

    neutral_zeros = {
        "HeadYaw": 0.0,
        "HeadPitch": 0.0,

        "LShoulderPitch": 1.45,
        "LShoulderRoll": 0.15,
        "LElbowYaw": -1.20,
        "LElbowRoll": -0.50,
        "LWristYaw": 0.0,

        "RShoulderPitch": 1.45,
        "RShoulderRoll": -0.15,
        "RElbowYaw": 1.20,
        "RElbowRoll": 0.50,
        "RWristYaw": 0.0,

        "HipRoll": 0.0,
        "HipPitch": 0.0,
        "KneePitch": 0.0
    }

    return LaunchDescription([
        DeclareLaunchArgument(
            "urdf_path",
            default_value="/home/robot/pepper_ws/src/naoqi_driver2/share/urdf/pepper.urdf",
            description="Path to Pepper URDF file"
        ),

        DeclareLaunchArgument(
            "rviz_config",
            default_value="/home/robot/pepper_ws/src/pepper_action_generation/rviz/pepper_action_generation.rviz",
            description="RViz config file"
        ),

        DeclareLaunchArgument(
            "send_to_real_pepper",
            default_value="false",
            description="If true, slider movement is continuously sent to real Pepper"
        ),

        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            name="pepper_joint_gui",
            parameters=[
                {
                    "robot_description": robot_description,
                    "zeros": neutral_zeros,
                    "publish_default_positions": True,
                    "publish_default_velocities": False,
                    "publish_default_efforts": False,
                    "rate": 30
                }
            ],
            remappings=[
                ("/joint_states", "/preview_joint_states")
            ],
            output="screen"
        ),

        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="pepper_preview_robot_state_publisher",
            parameters=[
                {
                    "robot_description": robot_description,
                    "use_sim_time": False
                }
            ],
            remappings=[
                ("/joint_states", "/preview_joint_states")
            ],
            output="screen"
        ),

        Node(
            package="pepper_action_generation",
            executable="action_recorder",
            name="pepper_action_recorder",
            output="screen",
            parameters=[
                {
                    "joint_states_topic": "/preview_joint_states",
                    "output_file": "/home/robot/pepper_ws/src/pepper_social_skills/config/generated_pepper_actions.json",
                    "send_to_real_pepper": ParameterValue(send_to_real_pepper, value_type=bool),
                    "joint_command_topic": "/joint_angles",
                    "default_speed": 0.05,
                    "default_hold_sec": 1.0
                }
            ]
        ),

        Node(
            package="rviz2",
            executable="rviz2",
            name="pepper_action_rviz",
            arguments=["-d", rviz_config],
            output="screen"
        )
    ])
