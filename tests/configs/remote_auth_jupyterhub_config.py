c = get_config()

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# Authenticator -> remote user header
c.JupyterHub.authenticator_class = "jhubauthenticators.DataRemoteUserAuthenticator"
c.Authenticator.enable_auth_state = True

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 15

c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.networks = ["jh_test"]

# Before the user can select which image to spawn,
# user_options has to be enabled
c.SwarmSpawner.use_user_options = True

# Available docker images the user can spawn
c.SwarmSpawner.images = [
    {"image": "ucphhpc/base-notebook:latest", "name": "Basic Python Notebook"}
]
