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
    maintainer_email='vishal.shendge@igcv.fraunhofer.de',
    description='TODO: Package description',
    license='TODO: License declaration',
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
