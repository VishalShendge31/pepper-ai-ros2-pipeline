from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, EnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():

    nao_ip = LaunchConfiguration("nao_ip")
    openai_api_key = LaunchConfiguration("openai_api_key")
    openai_model = LaunchConfiguration("openai_model")
    require_wake_word = LaunchConfiguration("require_wake_word")

    return LaunchDescription([

        DeclareLaunchArgument("nao_ip", default_value="192.168.100.20"),
        DeclareLaunchArgument("host_ip", default_value="192.168.100.172"),
        DeclareLaunchArgument("dashboard_port", default_value="5000"),

        DeclareLaunchArgument(
            "openai_api_key",
            default_value=EnvironmentVariable("OPENAI_API_KEY", default_value=""),
        ),

        DeclareLaunchArgument("openai_model", default_value="gpt-4o-mini"),
        DeclareLaunchArgument("require_wake_word", default_value="false"),

        DeclareLaunchArgument("enable_naoqi_driver", default_value="true"),
        DeclareLaunchArgument("enable_whisper", default_value="true"),
        DeclareLaunchArgument("enable_openai_server", default_value="true"),
        DeclareLaunchArgument("enable_transcription_bridge", default_value="true"),
        DeclareLaunchArgument("enable_vlm", default_value="true"),
        DeclareLaunchArgument("enable_tts", default_value="true"),
        DeclareLaunchArgument("enable_dashboard", default_value="true"),
        DeclareLaunchArgument("enable_teleop", default_value="true"),
        DeclareLaunchArgument("enable_system_monitor", default_value="true"),

        LogInfo(msg="Starting Pepper full AI system..."),

        ExecuteProcess(
            condition=IfCondition(LaunchConfiguration("enable_naoqi_driver")),
            cmd=[
                "bash",
                "-c",
                [
                    "source /opt/ros/humble/setup.bash && "
                    "source ~/pepper_ws/install/setup.bash && "
                    "ros2 launch naoqi_driver naoqi_driver.launch.py nao_ip:=",
                    nao_ip,
                ],
            ],
            output="screen",
        ),

        TimerAction(
            period=5.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_whisper")),
                    package="pepper_audio_transcriber",
                    executable="whisper_transcriber",
                    name="whisper_transcriber",
                    output="screen",
                )
            ],
        ),

        TimerAction(
            period=8.0,
            actions=[
                ExecuteProcess(
                    condition=IfCondition(LaunchConfiguration("enable_openai_server")),
                    cmd=[
                        "bash",
                        "-c",
                        [
                            "source /opt/ros/humble/setup.bash && "
                            "source ~/pepper_ws/install/setup.bash && "
                            "ros2 launch openai_server openai_server_launch.py "
                            "openai_api_key:=",
                            openai_api_key,
                            " openai_model:=",
                            openai_model,
                        ],
                    ],
                    output="screen",
                )
            ],
        ),

        TimerAction(
            period=10.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_transcription_bridge")),
                    package="openai_bridge",
                    executable="transcription_to_openai",
                    name="transcription_to_openai",
                    output="screen",
                    parameters=[
                        {
                            "require_wake_word": require_wake_word,
                        }
                    ],
                )
            ],
        ),

        TimerAction(
            period=12.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_vlm")),
                    package="pepper_vlm",
                    executable="pepper_vlm_node",
                    name="pepper_vlm_node",
                    output="screen",
                )
            ],
        ),

        TimerAction(
            period=14.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_tts")),
                    package="pepper_speech",
                    executable="pepper_speech_node",
                    name="pepper_speech_node",
                    output="screen",
                )
            ],
        ),

        TimerAction(
            period=16.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_dashboard")),
                    package="pepper_dashboard",
                    executable="pepper_dashboard_server",
                    name="pepper_dashboard_server",
                    output="screen",
                )
            ],
        ),

        TimerAction(
            period=18.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_teleop")),
                    package="joy",
                    executable="joy_node",
                    name="joy_node",
                    output="screen",
                ),

                Node(
                    condition=IfCondition(LaunchConfiguration("enable_teleop")),
                    package="pepper_Ps4",
                    executable="teleop_ps4",
                    name="teleop_ps4",
                    output="screen",
                ),
            ],
        ),

        TimerAction(
            period=20.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_system_monitor")),
                    package="pepper_bringup",
                    executable="system_monitor",
                    name="pepper_system_monitor",
                    output="screen",
                )
            ],
        ),
    ])