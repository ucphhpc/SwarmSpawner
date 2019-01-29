# Configuration file for jupyterhub.
import os

c = get_config()

c.JupyterHub.spawner_class = 'jhub.SwarmSpawner'

c.JupyterHub.authenticator_class = 'jhubauthenticators.DummyAuthenticator'
c.DummyAuthenticator.password = 'password'

c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5

c.SwarmSpawner.jupyterhub_service_name = 'jupyterhub'

c.SwarmSpawner.networks = ["jupyterhub_default"]

c.SwarmSpawner.container_spec = {
    'args': ['/usr/local/bin/start-singleuser.sh',
             '--NotebookApp.ip=0.0.0.0',
             '--NotebookApp.port=8888',
             '--NotebookApp.allow_origin=http://127.0.0.1'],
    'env': {'JUPYTER_ENABLE_LAB': '1',
            'TZ': 'Europe/Copenhagen'}
}

c.SwarmSpawner.use_user_options = True

c.SwarmSpawner.dockerimages = [
    {'image': 'nielsbohr/slurm-notebook:edge',
     'name': 'Default jupyter notebook'},
    {'image': 'nielsbohr/hpc-notebook',
     'name': 'HPC Notebook',
     'args': ['/usr/bin/supervisord']}
]
