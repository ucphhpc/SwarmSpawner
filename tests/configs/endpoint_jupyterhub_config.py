"""A simple jupyter config file for testing the spawner."""
c = get_config()

c.JupyterHub.hub_ip = "0.0.0.0"

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

# The name of the service that's running the hub
c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.start_timeout = 60 * 15

# The name of the overlay network that everything's connected to
c.SwarmSpawner.networks = ["jh_test"]

c.SwarmSpawner.images = [
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Basic Python Notebook",
        "endpoint_spec": {"mode": "vip", "ports": {"8000": "8000"}},
    }
]

c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "just magnets"
