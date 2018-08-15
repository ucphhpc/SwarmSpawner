# This is the dockerfile that builds an image from this package that we
# can use for testing.

FROM jupyterhub/jupyterhub:0.9.1

ADD mig SwarmSpawner/mig
ADD setup.py SwarmSpawner/setup.py
ADD requirements.txt SwarmSpawner/requirements.txt
ADD version.py SwarmSpawner/version.py

RUN pip install jupyterhub-dummyauthenticator \
    jhub-authenticators

RUN cd SwarmSpawner \
    && pip install -r requirements.txt \
    && touch README.rst \
    && python setup.py install \
    && cd .. \
    && rm -r SwarmSpawner

# We'll need to mount the jupyter_config in the container when we
# run it.
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyter_config.py"]
