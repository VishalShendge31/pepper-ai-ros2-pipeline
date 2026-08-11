from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, EnvironmentVariable, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    nao_ip = LaunchConfiguration("nao_ip")
    robot_user = LaunchConfiguration("robot_user")
    openai_api_key = LaunchConfiguration("openai_api_key")
    openai_model = LaunchConfiguration("openai_model")
    require_wake_word = LaunchConfiguration("require_wake_word")
    whisper_language = LaunchConfiguration("whisper_language")

    animation_timeout_sec = LaunchConfiguration("animation_timeout_sec")
    stop_timeout_sec = LaunchConfiguration("stop_timeout_sec")
    return_to_neutral_after_animation = LaunchConfiguration("return_to_neutral_after_animation")
    return_to_neutral_after_stop = LaunchConfiguration("return_to_neutral_after_stop")
    neutral_return_mode = LaunchConfiguration("neutral_return_mode")
    neutral_speed = LaunchConfiguration("neutral_speed")
    neutral_hold_sec = LaunchConfiguration("neutral_hold_sec")

    social_config_file = PathJoinSubstitution([
        FindPackageShare("pepper_social_skills"),
        "config",
        "social_skills.yaml",
    ])

    actions_file = PathJoinSubstitution([
        FindPackageShare("pepper_social_skills"),
        "config",
        "pepper_actions.json",
    ])

    animations_config = PathJoinSubstitution([
        FindPackageShare("pepper_social_skills"),
        "config",
        "pepper_naoqi_animations.json",
    ])

    return LaunchDescription([
        DeclareLaunchArgument("nao_ip", default_value="192.168.100.20"),
        DeclareLaunchArgument("robot_user", default_value="nao"),
        DeclareLaunchArgument("host_ip", default_value="192.168.100.172"),
        DeclareLaunchArgument("dashboard_port", default_value="5000"),

        DeclareLaunchArgument(
            "openai_api_key",
            default_value=EnvironmentVariable("OPENAI_API_KEY", default_value=""),
        ),
        DeclareLaunchArgument("openai_model", default_value="gpt-4o-mini"),

        # This is consumed by whisper_transcriber. The old transcription bridge remains disabled.
        DeclareLaunchArgument("require_wake_word", default_value="true"),
        DeclareLaunchArgument("whisper_language", default_value="auto"),

        DeclareLaunchArgument("enable_naoqi_driver", default_value="true"),
        DeclareLaunchArgument("enable_whisper", default_value="true"),
        DeclareLaunchArgument("enable_openai_server", default_value="true"),
        DeclareLaunchArgument("enable_transcription_bridge", default_value="false"),
        DeclareLaunchArgument("enable_vlm", default_value="true"),
        DeclareLaunchArgument("enable_tts", default_value="true"),
        DeclareLaunchArgument("enable_dashboard", default_value="true"),
        DeclareLaunchArgument("enable_teleop", default_value="true"),
        DeclareLaunchArgument("enable_system_monitor", default_value="true"),
        DeclareLaunchArgument("enable_social_skills", default_value="true"),

        # Disabled by default for stable demos because NAOqi AnimatedSpeech already moves the body.
        # Enable manually when testing custom /joint_angles gestures.
        DeclareLaunchArgument("enable_gesture_node", default_value="false"),

        # Required for PS4 animation/behavior buttons on /pepper/animation_command.
        DeclareLaunchArgument("enable_animation_executor", default_value="true"),
        DeclareLaunchArgument("animation_timeout_sec", default_value="45.0"),
        DeclareLaunchArgument("stop_timeout_sec", default_value="15.0"),
        DeclareLaunchArgument("return_to_neutral_after_animation", default_value="true"),
        DeclareLaunchArgument("return_to_neutral_after_stop", default_value="true"),
        DeclareLaunchArgument("neutral_return_mode", default_value="fixed_joints"),
        DeclareLaunchArgument("neutral_speed", default_value="0.25"),
        DeclareLaunchArgument("neutral_hold_sec", default_value="0.5"),

        LogInfo(msg="Starting Pepper full AI social system..."),

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
                    parameters=[
                        {
                            "language": whisper_language,
                            "require_wake_word": ParameterValue(require_wake_word, value_type=bool),
                            "wake_words": [
                                "hey pepper",
                                "hello pepper",
                                "hi pepper",
                                "okay pepper",
                                "ok pepper",
                                "pepper",
                                "hallo pepper",
                                "hey pepper",
                                "okay pepper",
                                "ok pepper",
                                "hallo peppa",
                                "hey peppa",
                                "peppa",
                                "hallo paper",
                                "hey paper",
                                "paper",
                            ],
                        }
                    ],
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
                    parameters=[{"require_wake_word": ParameterValue(require_wake_word, value_type=bool)}],
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
                    parameters=[
                        {
                            "camera_topic": "/camera/front/image_raw",
                            "output_topic": "/smolvlm/output",
                            "process_interval_sec": 1.5,
                            "model_name": "HuggingFaceTB/SmolVLM-500M-Instruct",
                            "max_new_tokens": 160,
                            "emit_structured_fields": True,
                        }
                    ],
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
                    parameters=[
                        {
                            "input_topic": "/openai_response",
                            "speech_topic": "/speech",
                            "use_animated_speech": True,
                            "robot_ip": nao_ip,
                            "robot_user": robot_user,
                            "set_german_language": True,
                            "body_language_mode": "contextual",
                        }
                    ],
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
                    parameters=[
                        {
                            "deadzone": 0.35,
                            "neutral_calibration_samples": 25,
                            "movement_activation_frames": 2,
                            "publish_zero_repetitions": 3,
                            "max_linear_x": 0.12,
                            "max_linear_y": 0.08,
                            "max_angular_z": 0.25,
                            "enable_animation_buttons": True,
                            "animation_command_topic": "/pepper/animation_command",
                        }
                    ],
                ),
            ],
        ),

        TimerAction(
            period=19.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_animation_executor")),
                    package="pepper_social_skills",
                    executable="pepper_naoqi_animation_node",
                    name="pepper_naoqi_animation_node",
                    output="screen",
                    parameters=[
                        {
                            "robot_ip": nao_ip,
                            "robot_user": robot_user,
                            "command_topic": "/pepper/animation_command",
                            "status_topic": "/pepper/animation_status",
                            "animations_config": animations_config,
                            "animation_timeout_sec": ParameterValue(animation_timeout_sec, value_type=float),
                            "stop_timeout_sec": ParameterValue(stop_timeout_sec, value_type=float),
                            "return_to_neutral_after_animation": ParameterValue(return_to_neutral_after_animation, value_type=bool),
                            "return_to_neutral_after_stop": ParameterValue(return_to_neutral_after_stop, value_type=bool),
                            "neutral_return_mode": neutral_return_mode,
                            "neutral_speed": ParameterValue(neutral_speed, value_type=float),
                            "neutral_hold_sec": ParameterValue(neutral_hold_sec, value_type=float),
                            "allow_parallel_animations": False,
                        }
                    ],
                )
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

        TimerAction(
            period=22.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_social_skills")),
                    package="pepper_social_skills",
                    executable="social_skill_manager",
                    name="social_skill_manager",
                    output="screen",
                    parameters=[social_config_file],
                )
            ],
        ),

        TimerAction(
            period=23.0,
            actions=[
                Node(
                    condition=IfCondition(LaunchConfiguration("enable_gesture_node")),
                    package="pepper_social_skills",
                    executable="pepper_gesture_node",
                    name="pepper_gesture_node",
                    output="screen",
                    parameters=[
                        {
                            "vlm_topic": "/smolvlm/output",
                            "response_topic": "/openai_response",
                            "joint_topic": "/joint_angles",
                            "actions_file": actions_file,
                            "enable_wave_from_camera": True,
                            "enable_speech_gestures": True,
                            "wave_cooldown_sec": 8.0,
                            "speech_gesture_cooldown_sec": 2.5,
                            "min_speech_gesture_sec": 2.0,
                            "max_speech_gesture_sec": 8.0,
                        }
                    ],
                )
            ],
        ),
    ])
