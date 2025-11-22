from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="shawtie",
    version="1.0.1",
    author="Turbash Negi",
    author_email="negirawatdeepi@gmail.com",
    description="AI-powered file organization tool for Linux",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Turbash/shawtie",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "pydub>=0.25.0",
        "rich>=13.0.0",
        "Pillow>=9.0.0",
        "mutagen>=1.45.0",
    ],
    entry_points={
        "console_scripts": [
            "shawtie=shawtie.cli:main",
        ],
    },
)