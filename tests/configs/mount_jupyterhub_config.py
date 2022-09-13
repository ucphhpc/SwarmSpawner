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

# Before the user can select which image to spawn,
# user_options has to be enabled
c.SwarmSpawner.use_user_options = True

# Available docker images the user can spawn
# Additional settings including, access, mounts, placement
c.SwarmSpawner.images = [
    {
        "image": "ucphhpc/base-notebook:latest",
        "name": "Base Notebook",
        "mounts": sshfs_mount,
        "placement": {"constraints": []},
    }
]
