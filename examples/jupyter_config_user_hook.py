import os
import shelve
# Configuration file for jupyterhub.
user_start_id = 10000
cur_path = os.path.join('/srv/jupyterhub/')
db_path = os.path.join(cur_path, 'user_uid.db')

# Simple method to generate a uid for the user
def simple_user_id(spawner):
    user = spawner.user
    if hasattr(spawner.user, 'uid') and \
            spawner.user.uid is not None:
        spawner.log.info("Pre-Spawn, user {} already has id {}".format(user,
                                                                       user.uid))
        return False
    spawner.log.info("Pre-Spawn, creating id for {}".format(user))

    user_id = None
    with shelve.open(db_path) as db:
        ids = list(db.keys())
        if not ids:
            # First user
            new_id = str(user_start_id)
            db[new_id] = user.name
            user_id = new_id
        else:
            # check if user exists
            usernames = list(db.values())
            if user.name not in usernames:
                new_id = str(int(ids[-1]) + 1)
                db[new_id] = user.name
                user_id = new_id
            else:
                # fetch existing id
                for uid, username in db.items():
                    if username == user.name:
                        user_id = uid
                        break

    if not user_id:
        spawner.log.error("Pre-Spawn, failed to aquire a uid for {}".format(user))
        return False
    spawner.user.uid = user_id

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
    {'name': 'Base Notebook',
     'image': 'nielsbohr/base-notebook',
     'env': {'NB_USER': '{_service_owner}',
             'NB_UID': '{uid}',
             'HOME': '/home/{_service_owner}',
             'CHOWN_HOME': 'yes',
             'GRANT_SUDO': 'no'},
     'uid_gid': 'root',
     'command': "/bin/bash -c 'mkdir -p /home/{_service_owner}; /usr/local/bin/start-notebook.sh'"
    },
]
