from setuptools import setup, find_packages

setup(
    name='photo-organizer',
    version='1.0.0',
    description='摄影师批量整理活动照片交付工具',
    author='Photo Organizer',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click>=8.0.0',
        'Pillow>=9.0.0',
        'exifread>=3.0.0',
    ],
    entry_points={
        'console_scripts': [
            'photo=photo_organizer.cli:main',
        ],
    },
    python_requires='>=3.8',
)
