# This is the dockerfile that builds an image from this package that we
# can use for testing.

FROM jupyterhub/jupyterhub:0.7.2

ADD mig SwarmSpawner/mig
ADD setup.py SwarmSpawner/setup.py
ADD requirements SwarmSpawner/requirements
ADD version.py SwarmSpawner/version.py

RUN pip install jupyterhub-dummyauthenticator

RUN git clone https://github.com/rasmunk/jhub_remote_user_auth_mig_mount.git --single-branch --branch devel \
    && cd jhub_remote_user_auth_mig_mount \
    && pip install -r requirements.txt \
    && python setup.py install

RUN cd SwarmSpawner \
    && pip install -r requirements/base.txt \
    && touch README.rst \
    && python setup.py install

# We'll need to mount the jupyter_config in the container when we
# run it.
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyter_config.py"]