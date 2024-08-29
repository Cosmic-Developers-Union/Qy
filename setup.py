from setuptools import setup, find_packages
from pathlib import Path
import re
from pathlib import Path


def get_version():
    code = Path('qy/__init__.py').read_text(encoding='utf-8')
    return re.search(r"^__version__ = '([^']+)'", code, re.M).group(1)


setup(
    name='QyLang',
    version=get_version(),
    description='Qy Lang, a Lisp language implemented in and based on Python',
    long_description=Path('README.md').read_text(encoding='utf-8'),
    long_description_content_type='text/markdown',
    author='Ge',
    author_email='cosplox@outlook.com',
    url='https://github.com/Cosmic-Developers-Union/Qy',
    install_requires=[
        'lark>=1.2.2'
    ],
    packages=find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Lisp',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'qy=qy.cli:main',  # Assuming you have a CLI entry point
        ],
    },
    license='Apache License 2.0'
)
