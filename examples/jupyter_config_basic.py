# Configuration file for jupyterhub.
import os

c = get_config()
c.Application.log_level = "DEBUG"

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "password"

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5

c.SwarmSpawner.notebook_dir = "~/work"
c.SwarmSpawner.jupyterhub_service_name = "jhub-swarmspawner_jupyterhub"
c.SwarmSpawner.networks = ["jupyterhub_default"]

c.SwarmSpawner.images = [
    {"image": "ucphhpc/base-notebook:latest", "name": "Python Notebook"}
]

c.SwarmSpawner.container_spec = {
    "args": [
        "/usr/local/bin/start-singleuser.sh",
        "--ServerApp.ip=0.0.0.0",
        "--ServerApp.port=8888",
    ]
}
