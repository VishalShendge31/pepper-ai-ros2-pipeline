from glob import glob
from setuptools import setup

package_name = "pepper_custom_tts"

setup(
    name=package_name,
    version="0.1.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/scripts", glob("scripts/*.py")),
        ("share/" + package_name + "/scripts", glob("scripts/*.sh")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vishal",
    maintainer_email="shendge.vishal.vilas@gmail.com",
    description="ROS 2 bridge for custom Spark-TTS speech generation and Pepper audio playback.",
    license='Apache-2.0',
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "custom_tts_node = pepper_custom_tts.custom_tts_node:main",
        ],
    },
)
