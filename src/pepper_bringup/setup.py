from setuptools import setup
from glob import glob
import os

package_name = "pepper_bringup"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        (
            "share/" + package_name,
            ["package.xml"],
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
        (
            os.path.join("share", package_name, "scripts"),
            glob("scripts/*.sh"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vishal Shendge",
    maintainer_email="vishal@example.com",
    description="Bringup package for Pepper ROS 2 AI pipeline.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "system_monitor = pepper_bringup.system_monitor:main",
        ],
    },
)