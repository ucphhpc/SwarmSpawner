"""A simple jupyter config file for testing the spawner."""
c = get_config()

c.JupyterHub.spawner_class = 'mig.SwarmSpawner'
c.JupyterHub.hub_ip = '0.0.0.0'

# The name of the service that's running the hub
c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

# The name of the overlay network that everything's connected to
c.SwarmSpawner.networks = ["jh_test"]

c.SwarmSpawner.dockerimages = [
    {'image': 'jupyterhub/singleuser:0.8.1',
     'name': 'Default jupyterhub singleuser notebook'}
]

c.SwarmSpawner.container_spec = {
    'args': ['/usr/local/bin/start-singleuser.sh'],
    'Image': "jupyterhub/singleuser:0.8.1",
    "mounts": []
}

c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'
c.DummyAuthenticator.password = "just magnets"
