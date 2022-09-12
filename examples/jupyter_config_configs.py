# Configuration file for jupyterhub.
import os

c = get_config()

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "password"

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

c.JupyterHub.cleanup_servers = False

configs = [
    {
        "config_name": "swarmservice_munge_key",
        "filename": "/etc/munge/munge.key",
        "uid": "997",
        "gid": "993",
        "mode": 0o400,
    },
    {"config_name": "swarmservice_slurm_conf", "filename": "/etc/slurm/slurm.conf"},
]

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5

c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.networks = ["jupyterhub_default"]

c.SwarmSpawner.container_spec = {
    "command": "start-notebook.sh",
    "args": ["--NotebookApp.default_url=/lab"],
}

c.SwarmSpawner.configs = configs

c.SwarmSpawner.images = [
    {"image": "ucphhpc/slurm-notebook:latest", "name": "Slurm notebook"}
]
