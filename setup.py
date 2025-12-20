# setup.py
from setuptools import setup, find_packages
import os
import re

def read_readme():
    """READMEファイルを読み込む（エラーハンドリング付き）"""
    readme_path = 'README.md'
    if not os.path.exists(readme_path):
        readme_path = 'readme.md'  # フォールバック
    if os.path.exists(readme_path):
        try:
            with open(readme_path, encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    return "SessionSmith - Session save/load utility for Jupyter notebooks"


def get_version():
    """__init__.pyからバージョンを取得"""
    init_path = os.path.join('SessionSmith', '__init__.py')
    if os.path.exists(init_path):
        try:
            with open(init_path, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
        except Exception:
            pass
    return "0.1.1"  # フォールバック


setup(
    name="SessionSmith",
    version=get_version(),
    packages=find_packages(),
    install_requires=[],
    extras_require={
        "visualization": ["matplotlib>=3.5.0"],
        "all": ["matplotlib>=3.5.0"],
    },
    author="YutoTAKAGI",
    author_email="yutotkg.1040@gmail.com",
    description="Simple session save/load utility for Jupyter notebooks using pickle",
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    url="https://github.com/yut0takagi/SessionSmith",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering",
        "Framework :: Jupyter",
    ],
    python_requires='>=3.9',
    keywords="jupyter notebook session save load pickle serialization algorithm tracer visualization",
)
