#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='projects-edx-platform-extensions',
    version='1.1.19',
    description='Projects management extension for edX platform',
    long_description=open('README.rst').read(),
    author='edX',
    url='https://github.com/edx-solutions/projects-edx-platform-extensions.git',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "django>=1.8",
    ],
)
