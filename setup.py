#!/usr/bin/env python

from setuptools import setup
import shlex
from subprocess import check_output

GIT_HEAD_REV = check_output(shlex.split('git rev-parse --short HEAD')).strip().decode()

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(name='pytuyo',
      version='1.0+{}'.format(GIT_HEAD_REV),
      url="https://github.com/rabryan/pytuyo",
      description='Python Mitutoyo Interface',
      author='Richard Bryan',
      author_email='rabryan@lucidsci.com',
      py_modules=['pytuyo'],
      install_requires = requirements,
     )
