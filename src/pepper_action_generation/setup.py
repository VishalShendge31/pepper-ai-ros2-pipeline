from setuptools import find_packages, setup
from glob import glob
import os

package_name = "pepper_action_generation"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "rviz"), glob("rviz/*.rviz")),
        (os.path.join("share", package_name, "config"), glob("config/*.json")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="robot",
    maintainer_email="shendge.vishal.vilas@gmail.com",
    description="Pepper action generation package using RViz, joint sliders, and action recording.",
    license='Apache-2.0',
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "action_recorder = pepper_action_generation.action_recorder:main",
        ],
    },
)
