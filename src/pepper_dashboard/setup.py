from setuptools import setup

package_name = 'pepper_dashboard'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pepper',
    maintainer_email='pepper@example.com',
    description='Pepper ROS 2 dashboard server',
    license='MIT',
    entry_points={
        'console_scripts': [
            'pepper_dashboard_server = pepper_dashboard.pepper_dashboard_server:main',
        ],
    },
)
