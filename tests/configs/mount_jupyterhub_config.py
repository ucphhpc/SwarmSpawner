import os
from jhub.mount import SSHFSMounter

c = get_config()

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.debug_proxy = True

# Authenticator -> remote user header
c.JupyterHub.authenticator_class = "jhubauthenticators.DataRemoteUserAuthenticator"
c.DataRemoteUserAuthenticator.data_headers = ["Mount"]
c.Authenticator.enable_auth_state = True

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"
# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 15

c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.networks = ["jh_test"]

notebook_dir = os.environ.get("NOTEBOOK_DIR") or "/home/jovyan/work/"
c.SwarmSpawner.notebook_dir = notebook_dir

sshfs_mount = [
    SSHFSMounter(
        {
            "type": "volume",
            "driver_config": "ucphhpc/sshfs:latest",
            "driver_options": {
                "sshcmd": "{sshcmd}",
                "id_rsa": "{id_rsa}",
                "one_time": "True",
                "allow_other": "",
                "reconnect": "",
                "port": "2222",
            },
            "source": "sshvolume-user-{username}",
            "target": "/home/jovyan/work",
            "labels": {"keep": "False"},
        }
    )
]

# 'args' is the command to run inside the service
# These are run inside every service
c.SwarmSpawner.container_spec = {
    "command": "start-notebook.sh",
    "args": ["--NotebookApp.default_url=/lab"],
}

# Before the user can select which image to spawn,
# user_options has to be enabled
c.SwarmSpawner.use_user_options = True

# Available docker images the user can spawn
# Additional settings including, access, mounts, placement
c.SwarmSpawner.images = [
    {
        "image": "nielsbohr/base-notebook:latest",
        "name": "Base Notebook",
        "mounts": sshfs_mount,
        "placement": {"constraints": []},
    }
]
