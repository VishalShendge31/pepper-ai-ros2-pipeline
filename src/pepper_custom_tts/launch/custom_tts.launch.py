import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def launch_setup(context, *args, **kwargs):
    package_share = FindPackageShare("pepper_custom_tts")

    start_server = LaunchConfiguration("start_server")
    venv_python = LaunchConfiguration("venv_python")
    server_host = LaunchConfiguration("server_host")
    server_port = LaunchConfiguration("server_port")
    spark_repo_dir = LaunchConfiguration("spark_repo_dir")
    model_name_or_path = LaunchConfiguration("model_name_or_path")
    spark_tts_dir = LaunchConfiguration("spark_tts_dir")
    output_dir = LaunchConfiguration("output_dir")
    device = LaunchConfiguration("device")
    default_emotion = LaunchConfiguration("default_emotion")
    max_new_tokens = LaunchConfiguration("max_new_tokens")
    temperature = LaunchConfiguration("temperature")
    top_k = LaunchConfiguration("top_k")
    top_p = LaunchConfiguration("top_p")
    playback_mode = LaunchConfiguration("playback_mode")
    robot_ip = LaunchConfiguration("robot_ip")
    robot_user = LaunchConfiguration("robot_user")
    input_topic = LaunchConfiguration("input_topic")

    server_script = PathJoinSubstitution([
        package_share,
        "scripts",
        "spark_tts_server.py",
    ])

    server_process = ExecuteProcess(
        condition=IfCondition(start_server),
        cmd=[
            venv_python,
            server_script,
            "--host", server_host,
            "--port", server_port,
            "--spark-repo-dir", spark_repo_dir,
            "--model-name-or-path", model_name_or_path,
            "--spark-tts-dir", spark_tts_dir,
            "--output-dir", output_dir,
            "--device", device,
            "--default-emotion", default_emotion,
            "--max-new-tokens", max_new_tokens,
            "--temperature", temperature,
            "--top-k", top_k,
            "--top-p", top_p,
        ],
        output="screen",
    )

    tts_node = Node(
        package="pepper_custom_tts",
        executable="custom_tts_node",
        name="pepper_custom_tts",
        output="screen",
        parameters=[
            PathJoinSubstitution([
                package_share,
                "config",
                "pepper_custom_tts.yaml",
            ]),
            {
                "input_topic": input_topic,
                "tts_server_url": ["http://", server_host, ":", server_port, "/tts"],
                "default_emotion": default_emotion,
                "playback_mode": playback_mode,
                "robot_ip": robot_ip,
                "robot_user": robot_user,
            },
        ],
    )

    return [server_process, tts_node]


def generate_launch_description():
    home = os.path.expanduser("~")
    workspace_root = os.path.join(home, "pepper_ws")
    custom_tts_root = os.path.join(workspace_root, "custom_tts")

    return LaunchDescription([
        DeclareLaunchArgument("start_server", default_value="true"),
        DeclareLaunchArgument(
            "venv_python",
            default_value=os.path.join(workspace_root, "sparktts_venv", "bin", "python3"),
            description="Python executable inside the Spark-TTS virtual environment.",
        ),
        DeclareLaunchArgument("server_host", default_value="127.0.0.1"),
        DeclareLaunchArgument("server_port", default_value="8765"),
        DeclareLaunchArgument("spark_repo_dir", default_value=os.path.join(custom_tts_root, "Spark-TTS")),
        DeclareLaunchArgument(
            "model_name_or_path",
            default_value="Vishalshendge3198/spark_tts_finetune",
            description="Use the Hugging Face model ID exactly as given in the model card.",
        ),
        DeclareLaunchArgument("spark_tts_dir", default_value=os.path.join(custom_tts_root, "Spark-TTS-0.5B")),
        DeclareLaunchArgument("output_dir", default_value="/tmp/pepper_custom_tts"),
        DeclareLaunchArgument("device", default_value="auto", description="auto, cuda, cuda:0, or cpu"),
        DeclareLaunchArgument("default_emotion", default_value="neutral"),
        DeclareLaunchArgument("max_new_tokens", default_value="2048"),
        DeclareLaunchArgument("temperature", default_value="0.8"),
        DeclareLaunchArgument("top_k", default_value="50"),
        DeclareLaunchArgument("top_p", default_value="1.0"),
        DeclareLaunchArgument("input_topic", default_value="/openai_response"),
        DeclareLaunchArgument("playback_mode", default_value="pepper_ssh"),
        DeclareLaunchArgument("robot_ip", default_value="192.168.100.20"),
        DeclareLaunchArgument("robot_user", default_value="nao"),
        OpaqueFunction(function=launch_setup),
    ])
