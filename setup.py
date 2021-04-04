import os
from setuptools import setup
from pathlib import Path

CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
HOME_DIRECTORY = str(Path.home())


setup(name='dns_cached_resolver',
      version='1.0',
      description='DNS cached resolver.',
      author='Vladyslav Barbanyagra',
      author_email='mrcontego@gmail.com',
      install_requires=open(os.path.join(CURRENT_DIRECTORY, 'requirements.txt')).readlines(),
      entry_points={
            'console_scripts': ['dns_cached_resolver=main.dns_cached_resolver:main'],
      },
      packages=['main'],
      data_files=[(('dns_cached_resolver_resources'), ['resources/config.ini'])])
