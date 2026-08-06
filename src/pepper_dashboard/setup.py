from setuptools import find_packages, setup

package_name = 'pepper_dashboard'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robot',
    maintainer_email='shendge.vishal.vilas@gmail.com',
    description='Flask web dashboard server for monitoring Pepper camera feeds and robot status.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'pepper_dashboard_server = pepper_dashboard.pepper_dashboard_server:main',
        ],
    },
    package_data={
        'pepper_dashboard': ['static/*.png', 'static/*.jpg'],
    },
)
