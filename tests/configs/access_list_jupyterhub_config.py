"""A simple jupyter config file for testing the spawner."""
from jhub.access import AccessLists

c = get_config()

c.JupyterHub.hub_ip = "0.0.0.0"

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

# The name of the service that's running the hub
c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.start_timeout = 60 * 15

# The name of the overlay network that everything's connected to
c.SwarmSpawner.networks = ["jh_test"]

# Access Limitations
access_groups = {"admins": ["admin_user"]}
c.SwarmSpawner.enable_access_system = True
c.SwarmSpawner.access_system = AccessLists(access_groups)

c.SwarmSpawner.images = [
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Basic Python Notebook",
    },
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Restricted Notebook",
        "access": {
            "groups": ["admins"],
        },
    },
]

c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "just magnets"
