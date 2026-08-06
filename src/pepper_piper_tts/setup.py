from setuptools import find_packages, setup

package_name = 'pepper_piper_tts'

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
    description='Piper neural TTS node that synthesizes speech audio for Pepper.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'pepper_piper_node = pepper_piper_tts.pepper_piper_node:main'
        ],
    },
)
