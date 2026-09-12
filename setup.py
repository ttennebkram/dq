"""Packaging metadata readable by older Python 3 interpreters."""

import os
import re
from setuptools import find_packages, setup

project = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(project, 'README.md'), encoding='utf-8') as stream:
    readme = stream.read()
with open(os.path.join(project, 'src', 'dq', '__init__.py'), encoding='utf-8') as stream:
    version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", stream.read()).group(1)

setup(
    name='dq',
    version=version,
    description='Lightweight data-quality reports for search indexes',
    long_description=readme,
    long_description_content_type='text/markdown',
    python_requires='>=3.4.10',
    package_dir={'': 'src'},
    packages=find_packages('src'),
    install_requires=[],
    entry_points={'console_scripts': ['dq=dq.cli:main']},
)
