# This is the dockerfile that builds an image from this package that we
# can use for testing.
FROM jupyterhub/jupyterhub:1.1.0
MAINTAINER Rasmus Munk <rasmus.munk@nbi.ku.dk>

ENV JHUB_DIR=/usr/local/share/jupyterhub
ENV JHUB_SRV_DIR=/srv/jupyterhub
ENV NEW_PAGES_DIR=$JHUB_SRV_DIR/pages

ADD jhub SwarmSpawner/jhub
ADD setup.py SwarmSpawner/setup.py
ADD requirements.txt SwarmSpawner/requirements.txt
ADD requirements-dev.txt SwarmSpawner/requirements-dev.txt
ADD tests/requirements.txt SwarmSpawner/tests/requirements.txt
ADD version.py SwarmSpawner/version.py

COPY pages $NEW_PAGES_DIR

RUN cp -r $NEW_PAGES_DIR/templates/* $JHUB_DIR/templates/ \
    && cp -r $NEW_PAGES_DIR/static/* $JHUB_DIR/static/

RUN cd SwarmSpawner \
    && touch README.rst \
    && python3 setup.py install \
    && cd .. \
    && rm -r SwarmSpawner

WORKDIR $JHUB_SRV_DIR

RUN touch $JHUB_SRV_DIR/jupyterhub_config.py \
    && echo "c.JupyterHub.data_files_path = '/usr/local/share/jupyterhub'" > $JHUB_SRV_DIR/jupyterhub_config.py

CMD ["jupyterhub"]
