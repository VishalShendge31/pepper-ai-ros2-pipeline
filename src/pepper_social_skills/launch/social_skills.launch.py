from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    social_config_file = PathJoinSubstitution([
        FindPackageShare('pepper_social_skills'),
        'config',
        'social_skills.yaml',
    ])

    actions_file = PathJoinSubstitution([
        FindPackageShare('pepper_social_skills'),
        'config',
        'pepper_actions.json',
    ])

    return LaunchDescription([
        DeclareLaunchArgument('enable_gesture_node', default_value='false'),

        Node(
            package='pepper_social_skills',
            executable='social_skill_manager',
            name='social_skill_manager',
            output='screen',
            parameters=[social_config_file],
        ),

        Node(
            condition=IfCondition(LaunchConfiguration('enable_gesture_node')),
            package='pepper_social_skills',
            executable='pepper_gesture_node',
            name='pepper_gesture_node',
            output='screen',
            parameters=[{
                'vlm_topic': '/smolvlm/output',
                'response_topic': '/openai_response',
                'joint_topic': '/joint_angles',
                'actions_file': actions_file,
                'enable_wave_from_camera': True,
                'enable_speech_gestures': True,
            }],
        ),
    ])
