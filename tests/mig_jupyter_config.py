import os

c = get_config()
pwd = os.path.dirname(__file__)

c.JupyterHub.spawner_class = 'mig.SwarmSpawner'
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

c.JupyterHub.cleanup_servers = True

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5

c.SwarmSpawner.jupyterhub_service_name = 'jupyterhub'

c.SwarmSpawner.networks = ["jh_test"]

notebook_dir = os.environ.get('NOTEBOOK_DIR') or '/home/jovyan/work/'
c.SwarmSpawner.notebook_dir = notebook_dir

mounts = [{'type': 'volume',
           'driver_config': 'rasmunk/sshfs:latest',
           'driver_options': {'sshcmd': '{sshcmd}', 'id_rsa': '{id_rsa}',
                              'big_writes': '', 'allow_other': '',
                              'reconnect': '', 'port': '2222'},
           'source': 'sshvolume-user-{username}',
           'target': '/home/jovyan/work'
           }]

# 'args' is the command to run inside the service
# These are run inside every service
c.SwarmSpawner.container_spec = {
    'args': ['/usr/local/bin/start-singleuser.sh']
}

# Before the user can select which image to spawn,
# user_options has to be enabled
c.SwarmSpawner.use_user_options = True

# Available docker images the user can spawn
c.SwarmSpawner.dockerimages = [
    {'image': 'jupyter/base-notebook:30f16d52126f',
     'name': 'Minimal python notebook'},
    {'image': 'nielsbohr/base-notebook:latest',
     'name': 'Image with automatic {replace_me} mount, supports Py2/3 and R,',
     'mounts': mounts}
]

# Authenticator -> remote user header
c.JupyterHub.authenticator_class = 'jhub_remote_user_auth_mig_mount' \
                                   '.remote_user_auth' \
                                   '.MIGMountRemoteUserAuthenticator'

# Limit cpu/mem to 4 cores/8 GB mem
# During congestion, kill random internal processes to limit
# available load to 1 core/ 2GB mem
c.SwarmSpawner.resource_spec = {
    'cpu_limit': int(8 * 1e9),
    'mem_limit': int(8192 * 1e6),
    'cpu_reservation': int(1 * 1e9),
    'mem_reservation': int(2048 * 1e6),
}
