c = get_config()

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# Authenticator
c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "just magnets"

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 15

c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.networks = ["jh_test"]

# Before the user can select which image to spawn,
# user_options has to be enabled


# Available docker images the user can spawn
c.SwarmSpawner.images = [
    {"image": "ucphhpc/base-notebook:latest", "name": "Basic Python Notebook"},
    {"image": "ucphhpc/base-notebook:latest", "name": "Basic Python Notebook 2"},
]

# -1 should mean unlimited
c.SwarmSpawner.container_spec = {"ulimit": {"soft": "-1", "hard": "-1"}}
