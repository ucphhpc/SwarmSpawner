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
    'env': {'JUPYTER_ENABLE_LAB': '1',
            'TZ': 'Europe/Copenhagen'}
}

c.SwarmSpawner.use_user_options = True

mounts = [{'type': 'bind',
           'source': '/tmp',
           'target': '/home/jovyan/tmpdir1'}]

c.SwarmSpawner.dockerimages = [
    {'image': 'nielsbohr/slurm-notebook:latest',
     'name': 'Default jupyter notebook',
     'command': "/bin/bash -c 'mkdir -p /home/jovyan/{tmpdir1,tempdir2}; "
     "/usr/bin/supervisord'",
     'mounts': mounts}
]
