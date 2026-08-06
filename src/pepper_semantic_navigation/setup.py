from setuptools import setup, find_packages
import os
from glob import glob

package_name = "pepper_semantic_navigation"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "docs"), glob("docs/*.md")),
        (os.path.join("share", package_name, "scripts"), glob("scripts/*.py")),
    ],
    install_requires=["setuptools", "PyYAML"],
    zip_safe=True,
    maintainer="robot",
    maintainer_email="shendge.vishal.vilas@gmail.com",
    description="Autonomous navigation, mapping, semantic waypoint, and dashboard launch layer for Pepper.",
    license='Apache-2.0',
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "pepper_laser_filter = pepper_semantic_navigation.pepper_laser_filter:main",
            "semantic_waypoint_node = pepper_semantic_navigation.semantic_waypoint_node:main",
        ],
    },
)
