import os
from jhubauthenticators import RegexUsernameParser

c = get_config()

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# Authenticator -> Remote-User header value
c.JupyterHub.authenticator_class = "jhubauthenticators.HeaderAuthenticator"
c.Authenticator.enable_auth_state = True
c.HeaderAuthenticator.user_external_allow_attributes = ["mount_data"]

notebook_dir = os.environ.get("NOTEBOOK_DIR") or os.path.join(
    os.sep, "home", "jovyan", "work"
)
c.JupyterHub.spawner_class = "jhub.SwarmSpawner"
# First pulls can be really slow, so lt's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 15
c.SwarmSpawner.notebook_dir = notebook_dir
c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"
c.SwarmSpawner.networks = ["jh_test"]

sshfs_mount = [
    SSHFSMounter(
        {
            "type": "volume",
            "driver_config": {
                "name": "ucphhpc/sshfs:latest",
                "options": {
                    "sshcmd": "{username}@{targetHost}:{targetPath}",
                    "id_rsa": "{privateKey}",
                    "port": "{port}",
                    "ephemeral": "True",
                    "allow_other": "",
                    "reconnect": "",
                },
            },
            "source": "sshvolume-user-{name}",
            "target": notebook_dir,
        }
    )
]

# Available docker images the user can spawn
# Additional settings including, mounts, placement
c.SwarmSpawner.images = [
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Base Notebook",
        "mounts": sshfs_mount,
    }
]

# Which user state varibales should be used to format the service config
c.SwarmSpawner.user_format_attributes = ["mount_data", "name"]


c.SwarmSpawner.container_spec = {
    "args": [
        "/usr/local/bin/start-singleuser.sh",
        "--ServerApp.ip=0.0.0.0",
        "--ServerApp.port=8888",
    ]
}
