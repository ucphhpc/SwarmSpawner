# Configuration file for jupyterhub.
import os

c = get_config()

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "password"

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5
c.SwarmSpawner.notebook_dir = "~/work"
c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"
c.SwarmSpawner.networks = ["jupyterhub_default"]


c.SwarmSpawner.images = [
    {"image": "ucphhpc/base-notebook:latest", "name": "Default jupyter notebook"},
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Base Notebook",
    },
]
