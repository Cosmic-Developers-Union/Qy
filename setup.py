from setuptools import setup, find_packages
from pathlib import Path
setup(
    name='qy',
    version='0.0.1',
    description='Qy Lang, a Lisp language implemented in and based on Python',
    long_description=Path('README.md').read_text(encoding='utf-8'),
    long_description_content_type='text/markdown',
    author='Ge',
    author_email='cosplox@outlook.com',
    url='https://github.com/Cosmic-Developers-Union/Qy',
    packages=find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Lisp',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    install_requires=[
        # Add any dependencies your package requires here
    ],
    entry_points={
        'console_scripts': [
            'qy=qy.cli:main',  # Assuming you have a CLI entry point
        ],
    },
    license='Apache License 2.0'
)
