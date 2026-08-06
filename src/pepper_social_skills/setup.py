from setuptools import setup
from glob import glob
import os

package_name = "pepper_social_skills"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vishal",
    maintainer_email="shendge.vishal.vilas@gmail.com",
    description="ROS 2 social skill architecture for Pepper humanoid robot.",
    license='Apache-2.0',
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            'social_skill_manager = pepper_social_skills.social_skill_manager:main',
            'pepper_gesture_node = pepper_social_skills.pepper_gesture_node:main',
            'pepper_naoqi_animation_node = pepper_social_skills.pepper_naoqi_animation_node:main',
        ],
    },
)
