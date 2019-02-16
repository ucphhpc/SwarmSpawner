# Configuration file for jupyterhub.
user_start_id = 10000

# Simple method to generate a uid for the user
def simple_user_id(spawner):
    user = spawner.user
    if hasattr(spawner.user, 'uid') and \
            spawner.user.uid is not None:
        spawner.log.info("Pre-Spawn, user {} already has id {}".format(user,
                                                                       user.uid))
        return False

    spawner.log.info("Pre-Spawn, creating id for {}".format(user))
    cur_id = None
    # If used for real, remember to lock file
    try:
        with open('current_user_id', 'r') as user_file:
            cur_id = user_file.readline()
    except IOError as err:
        spawner.log.error("Could not open current_user_id {}".format(err))

    if cur_id is None:
        new_id = user_start_id
    else:
        new_id = int(cur_id) + 1
    try:
        with open('current_user_id', 'w') as user_file:
            user_file.write(str(new_id))
    except IOError as err:
        spawner.log.error("Could not open current_user_id {}".format(err))
        return False

    spawner.user.uid = str(new_id)

c = get_config()

c.JupyterHub.spawner_class = 'jhub.SwarmSpawner'

c.JupyterHub.authenticator_class = 'jhubauthenticators.DummyAuthenticator'
c.DummyAuthenticator.password = 'password'

c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'

c.JupyterHub.cleanup_servers = False

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 5

c.SwarmSpawner.jupyterhub_service_name = 'jupyterhub'
c.SwarmSpawner.networks = ["jupyterhub_default"]

c.SwarmSpawner.use_user_options = True

c.SwarmSpawner.container_spec = {
    # The command to run inside the service
    'env': {'JUPYTER_ENABLE_LAB': '1'}
}

c.SwarmSpawner.pre_spawn_hook = simple_user_id

c.SwarmSpawner.dockerimages = [
    {'name': 'Slurm Notebook',
     'image': 'nielsbohr/slurm-notebook:edge',
     'env': {'NB_USER': '{service_owner}',
            'NB_UID': '{uid}',
            'NB_GID': '100',
            'HOME': '{service_owner}',
            'CHOWN_HOME': 'yes',
            'CHOWN_HOME_OPTS': '-R',
            'GRANT_SUDO': 'no'},
     'uid_gid': 'root'
    }
]
