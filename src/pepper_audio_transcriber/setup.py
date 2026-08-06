from setuptools import find_packages, setup

package_name = 'pepper_audio_transcriber'

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
    maintainer='root',
    maintainer_email='shendge.vishal.vilas@gmail.com',
    description='Streaming Faster-Whisper transcription of Pepper microphone audio with VAD.',
    license='Apache-2.0',
    # REMOVED: tests_require=['pytest'] - Line 18 DELETED
    entry_points={
        'console_scripts': [
            'whisper_transcriber = pepper_audio_transcriber.whisper_transcriber:main',
        ],
    },
)
