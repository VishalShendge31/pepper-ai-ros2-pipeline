from setuptools import setup
from glob import glob
import os

package_name = "pepper_navigation"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "rviz"), glob("rviz/*.rviz")),
        (os.path.join("share", package_name, "maps"), glob("maps/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="robot",
    maintainer_email="shendge.vishal.vilas@gmail.com",
    description="Pepper RViz, SLAM, and navigation launch package",
    license='Apache-2.0',
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [],
    },
)
