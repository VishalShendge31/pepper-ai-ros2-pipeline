from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='openai_bridge',
            executable='transcription_to_openai',
            name='transcription_to_openai',
            output='screen',
            parameters=[
                {'reset_conversation': True},
                {'pre_prompt': (
    'You are a helpful robot assistant. Respond concisely in German in one short sentence. '
    'You will be provided with a [Visual Context] block containing a description of what you are currently seeing through your camera. '
    'Use this visual context to help answer the user\'s question creatively, but do not explicitly mention that you "see a description". Talk as if you are looking at it with your own eyes.'
                )}
            ]
        )
    ])
