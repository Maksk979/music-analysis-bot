from setuptools import setup, find_packages

setup(
    name="track-analyzer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "librosa",
        "numpy",
        "fastapi",
        "uvicorn",
        "python-multipart",
        "aiofiles",
        "soundfile",
        "pytest",
    ],
)
