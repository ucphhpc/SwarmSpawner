import os
from setuptools import setup, find_packages

cur_dir = os.path.abspath(os.path.dirname(__file__))

# Get the current package version.
version_ns = {}
with open(os.path.join(cur_dir, 'version.py')) as f:
    exec(f.read(), {}, version_ns)

long_description = open('README.rst').read()

setup(
    name='jhub-swarmspawner',
    version=version_ns['__version__'],
    long_description=long_description,
    description="""
                 SwarmSpawner enables JupyterHub to spawn jupyter
                 notebooks across a Docker Swarm cluster
                """,
    url='https://github.com/rasmunk/SwarmSpawner',
    # Author details
    author='Rasmus Munk',
    author_email='rasmus.munk@nbi.ku.dk',
    license='BSD',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords=['Interactive', 'Interpreter', 'Shell', 'Web'],
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'docker>=3.4.1',
        'jupyterhub>=0.9.2'
    ]
)
