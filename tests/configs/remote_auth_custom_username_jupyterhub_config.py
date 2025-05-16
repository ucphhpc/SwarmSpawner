c = get_config()
from jhubauthenticators import RegexUsernameParser

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# Authenticator -> remote user header
c.JupyterHub.authenticator_class = "jhubauthenticators.HeaderAuthenticator"
c.Authenticator.enable_auth_state = True
c.HeaderAuthenticator.user_external_allow_attributes = ["mount_data"]
# RegexUsernameParser
c.HeaderAuthenticator.header_parser_classes = {"auth": RegexUsernameParser}
# Email regex
RegexUsernameParser.username_extract_regex = (
    "([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
)
RegexUsernameParser.replace_extract_chars = {"@": "_", ".": "_"}

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

c.SwarmSpawner.container_spec = {
    "args": [
        "/usr/local/bin/start-singleuser.sh",
        "--ServerApp.ip=0.0.0.0",
        "--ServerApp.port=8888",
    ]
}
