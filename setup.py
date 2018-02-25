#!/usr/bin/env python
from setuptools import setup, find_packages

#
# Basic installation only installs dependencies that are required by both
# tools (enrolled and commissioner). To use the package as an enrollment
# daemon, install the extra dependencies for enrolled using:
#
#  $ pip install spinet[enrolled]
#
# To install the extra dependencies needed by the commissioner, run:
#
#  $ pip install spinet[commissioner]
#

setup(
    name='spinet',
    version='0.0.1',
    description='A System for Provisioning of IoT Networks',
    author='Jan Janak',
    author_email='janakj@cs.columbia.edu',
    packages=find_packages(),
    install_requires=[
        'blinker',
        'cached-property',
        'pyroute2',
        'pyopenssl'
    ],

    extras_require={
        'enrolled': [
            'flask',
            'proquint'
        ],
        'commissioner': [
            'tabulate',
            'netifaces',
            'urllib3'
        ],
        'label': [
            'pyopenssl',
            'tabulate',
            'netifaces',
            'cbor'
        ]
    },

    entry_points={
        'console_scripts': [
            'enrolled=spinet.enrolled.__main__:main',
            'device-label=spinet.enrolled.label:main',
            'commissioner=spinet.cms.__main__:main'
        ]
    }
)
