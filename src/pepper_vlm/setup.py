from setuptools import find_packages, setup

package_name = 'pepper_vlm'

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
    description='Vision-language model (SmolVLM) node for Pepper camera-based perception and multimodal interaction.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'pepper_vlm_node = pepper_vlm.pepper_vlm_node:main',
            'pepper_camera_face_preprocessor = pepper_vlm.pepper_camera_face_preprocessor:main',
            'detection_layer = pepper_vlm.detection_layer:main',
        ],
    },
)
