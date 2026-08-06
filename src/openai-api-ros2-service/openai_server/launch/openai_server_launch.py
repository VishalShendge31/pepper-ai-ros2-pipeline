from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'openai_api_key',
            default_value='ENTER YOUR OPENAI API KEY HERE',
            description='Do not accidentally push your API key to a public repo'
        ),
        DeclareLaunchArgument(
            'openai_model',
            default_value='gpt-3.5-turbo',
            description='The OpenAI model to use (e.g. gpt-4o, gpt-3.5-turbo,gpt-4-0125-preview)'
        ),
        Node(
            package='openai_server',
            executable='openai_server_node',  # Name deines Executables (siehe CMake)
            name='openai_server',
            parameters=[{
                'openai_api_key': LaunchConfiguration('openai_api_key'),
                'openai_model': LaunchConfiguration('openai_model')
            }]
        )
    ])
