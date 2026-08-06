from setuptools import find_packages, setup

package_name = 'pepper_speech'

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
    description='ROS 2 nodes that bridge LLM text responses to Pepper speech, including built-in TTS and Orpheus TTS.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'pepper_speech_node = pepper_speech.pepper_speech_node:main',
            'orpheus_speech_node = pepper_speech.orpheus_speech_node:main',
        ],
    },
)
