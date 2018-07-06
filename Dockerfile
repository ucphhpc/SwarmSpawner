# This is the dockerfile that builds an image from this package that we
# can use for testing.

FROM jupyterhub/jupyterhub:0.8.1

ADD mig SwarmSpawner/mig
ADD setup.py SwarmSpawner/setup.py
ADD requirements.txt SwarmSpawner/requirements.txt
ADD version.py SwarmSpawner/version.py

RUN pip install jupyterhub-dummyauthenticator

RUN git clone https://github.com/rasmunk/jhub_remote_auth_mount.git \
    && cd jhub_remote_auth_mount \
    && git checkout 16deb4a302ccabbec1048f2ca42e0fab0c02e736 \
    && pip install -r requirements.txt \
    && python setup.py install

RUN cd SwarmSpawner \
    && pip install -r requirements.txt \
    && touch README.rst \
    && python setup.py install

# We'll need to mount the jupyter_config in the container when we
# run it.
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyter_config.py"]
