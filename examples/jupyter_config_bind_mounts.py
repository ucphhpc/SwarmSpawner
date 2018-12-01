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

notebook_dir = os.environ.get('NOTEBOOK_DIR') or '/home/jovyan/work'
c.SwarmSpawner.notebook_dir = notebook_dir

mounts = [{'type': 'bind',
           'source': '/tmp',
           'target': notebook_dir}]

c.SwarmSpawner.container_spec = {
    # The command to run inside the service
    'args': ['/usr/local/bin/start-singleuser.sh',
             '--NotebookApp.ip=0.0.0.0',
             '--NotebookApp.port=8888'],
    'env': {'JUPYTER_ENABLE_LAB': '1'},
    'mounts': mounts
}