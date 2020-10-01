import os
from setuptools import setup, find_packages

cur_dir = os.path.abspath(os.path.dirname(__file__))


def read(path):
    with open(path, "r") as _file:
        return _file.read()


def read_req(name):
    path = os.path.join(cur_dir, name)
    return [req.strip() for req in read(path).splitlines() if req.strip()]


# Get the current package version.
version_ns = {}
with open(os.path.join(cur_dir, "version.py")) as f:
    exec(f.read(), {}, version_ns)

long_description = open("README.rst").read()
setup(
    name="jhub-swarmspawner",
    version=version_ns["__version__"],
    description="""SwarmSpawner enables JupyterHub to spawn jupyter
                notebooks across a Docker Swarm cluster""",
    long_description=long_description,
    author="Rasmus Munk",
    author_email="rasmus.munk@nbi.ku.dk",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    url="https://github.com/rasmunk/SwarmSpawner",
    license="BSD",
    keywords=["Interactive", "Interpreter", "Shell", "Web"],
    install_requires=read_req("requirements.txt"),
    extras_require={
        "dev": read_req("requirements-dev.txt"),
        "test": read_req(os.path.join("tests", "requirements.txt")),
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
