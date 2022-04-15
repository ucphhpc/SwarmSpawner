FROM jupyterhub/jupyterhub:2.2.2
LABEL MAINTAINER Rasmus Munk <rasmus.munk@nbi.ku.dk>

WORKDIR /app

ADD jhub SwarmSpawner/jhub
ADD setup.py SwarmSpawner/setup.py
ADD requirements.txt SwarmSpawner/requirements.txt
ADD requirements-dev.txt SwarmSpawner/requirements-dev.txt
ADD tests/requirements.txt SwarmSpawner/tests/requirements.txt
ADD version.py SwarmSpawner/version.py

RUN cd SwarmSpawner \
    && touch README.rst \
    && pip3 install .

WORKDIR /etc/jupyterhub

CMD ["jupyterhub"]
