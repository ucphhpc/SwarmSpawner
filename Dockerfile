# This is the dockerfile that builds an image from this package that we
# can use for testing.

FROM jupyterhub/jupyterhub:1.2

ADD jhub SwarmSpawner/jhub
ADD setup.py SwarmSpawner/setup.py
ADD requirements.txt SwarmSpawner/requirements.txt
ADD version.py SwarmSpawner/version.py

RUN cd SwarmSpawner \
    && pip3 install -r requirements.txt \
    && touch README.rst \
    && python3 setup.py install \
    && cd .. \
    && rm -r SwarmSpawner

CMD ["jupyterhub"]
