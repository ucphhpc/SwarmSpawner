"""
A Spawner for JupyterHub that runs each user's
server in a separate Docker Service
"""

import hashlib
import docker
from textwrap import dedent
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from docker.errors import APIError
from docker.utils import kwargs_from_env
from tornado import gen, web
from jupyterhub.spawner import Spawner
from traitlets import (
    default,
    Dict,
    Unicode,
    List,
    Bool,
    Int,
)


class UnicodeOrFalse(Unicode):
    info_text = 'a unicode string or False'

    def validate(self, obj, value):
        if not value:
            return value
        return super(UnicodeOrFalse, self).validate(obj, value)


class SwarmSpawner(Spawner):
    """A Spawner for JupyterHub using Docker Engine in Swarm mode

    Makes a list of docker images available for the user to spawn
    Specify in the jupyterhub configuration file which are allowed:
    e.g.

    c.JupyterHub.spawner_class = 'cassinyspawner.SwarmSpawner'
    # Available docker images the user can spawn
    c.SwarmSpawner.dockerimages = [
        '127.0.0.1:5000/nbi_jupyter_notebook'
    ]

    The images must be locally available before the user can spawn them
    """

    dockerimages = List(
        trait = Dict(),
        default_value = [{'image': '127.0.0.1:5000/nbi_jupyter_notebook',
                          'name': 'Image with default MiG Homedrive mount,'
                                  ' supports Py2/3 and R'}],
        minlen = 1,
        config = True,
        help = "Docker images that have been pre-pulled to the execution host."
    )

    form_template = Unicode("""
        <label for="dockerimage">Select a notebook image:</label>
        <select class="form-control" name="dockerimage" required autofocus>
            {option_template}
        </select>""",
        config = True, help = "Form template."
    )

    option_template = Unicode("""
        <option value="{image}">{name}</option>""",
        config = True, help = "Template for html form options."
    )

    _executor = None

    @default('options_form')
    def _options_form(self):
        """Return the form with the drop-down menu."""
        options = ''.join([
            self.option_template.format(image=di['image'], name=di['name'])
            for di in self.dockerimages
        ])
        return self.form_template.format(option_template=options)


    @property
    def executor(self, max_workers=1):
        """single global executor"""
        cls = self.__class__
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(max_workers)
        return cls._executor

    _client = None

    @property
    def client(self):
        """single global client instance"""
        cls = self.__class__

        if cls._client is None:
            kwargs = {}
            if self.tls_config:
                kwargs['tls'] = docker.tls.TLSConfig(**self.tls_config)
            kwargs.update(kwargs_from_env())
            client = docker.APIClient(version='auto', **kwargs)

            cls._client = client
        return cls._client

    service_id = Unicode()
    service_port = Int(8888, min=1, max=65535, config=True)
    service_image = Unicode("jupyterhub/singleuser", config=True)
    service_prefix = Unicode(
        "jupyter",
        config=True,
        help=dedent(
            """
            Prefix for service names. The full service name for a particular
            user will be <prefix>-<hash(username)>-<server_name>.
            """
        )
    )
    tls_config = Dict(
        config=True,
        help=dedent(
            """Arguments to pass to docker TLS configuration.
            Check for more info: http://docker-py.readthedocs.io/en/stable/tls.html
            """
        )
    )

    container_spec = Dict({}, config=True, help="Params to create the service")
    resource_spec = Dict(
        {}, config=True, help="Params about cpu and memory limits")

    placement = List([], config=True,
                     help=dedent(
                         """List of placement constraints into the swarm
                         """))

    networks = List([], config=True,
                    help=dedent(
                        """Additional args to create_host_config for service create
                        """))
    use_user_options = Bool(False, config=True,
                            help=dedent(
                                """the spawner will use the dict passed through the form
                                or as json body when using the Hub Api
                                """))
    jupyterhub_service_name = Unicode(config=True,
                                      help=dedent(
                                          """Name of the service running the JupyterHub
                                          """))

    @property
    def tls_client(self):
        """A tuple consisting of the TLS client certificate and key if they
        have been provided, otherwise None.

        """
        if self.tls_cert and self.tls_key:
            return (self.tls_cert, self.tls_key)
        return None

    _service_owner = None

    @property
    def service_owner(self):
        if self._service_owner is None:
            m = hashlib.md5()
            m.update(self.user.name.encode('utf-8'))
            self._service_owner = m.hexdigest()
        return self._service_owner

    @property
    def service_name(self):
        """
        Service name inside the Docker Swarm

        service_suffix should be a numerical value unique for user
        {service_prefix}-{service_owner}-{service_suffix}
        """
        if hasattr(self, "server_name") and self.server_name:
            server_name = self.server_name
        else:
            server_name = 1

        return "{}-{}-{}".format(self.service_prefix,
                                 self.service_owner,
                                 server_name
                                 )

    def load_state(self, state):
        super().load_state(state)
        self.service_id = state.get('service_id', '')

    def get_state(self):
        state = super().get_state()
        if self.service_id:
            state['service_id'] = self.service_id
        return state

    def _env_keep_default(self):
        """it's called in traitlets. It's a special method name.
        Don't inherit any env from the parent process"""
        return []

    def _public_hub_api_url(self):
        proto, path = self.hub.api_url.split('://', 1)
        _, rest = path.split(':', 1)
        return '{proto}://{name}:{rest}'.format(
            proto=proto,
            name=self.jupyterhub_service_name,
            rest=rest
        )

    def get_env(self):
        env = super().get_env()
        env.update(dict(
            JPY_USER=self.user.name,
            JPY_COOKIE_NAME=self.user.server.cookie_name,
            JPY_BASE_URL=self.user.server.base_url,
            JPY_HUB_PREFIX=self.hub.server.base_url
        ))

        if self.notebook_dir:
            env['NOTEBOOK_DIR'] = self.notebook_dir

        env['JPY_HUB_API_URL'] = self._public_hub_api_url()

        return env

    def _docker(self, method, *args, **kwargs):
        """wrapper for calling docker methods

        to be passed to ThreadPoolExecutor
        """
        m = getattr(self.client, method)
        return m(*args, **kwargs)

    def docker(self, method, *args, **kwargs):
        """Call a docker method in a background thread

        returns a Future
        """
        return self.executor.submit(self._docker, method, *args, **kwargs)

    @gen.coroutine
    def poll(self):
        """Check for a task state like `docker service ps id`"""
        service = yield self.get_service()
        if service is None:
            self.log.warn("Docker service not found")
            return 0

        task_filter = {'service': service['Spec']['Name']}
        tasks = yield self.docker(
            'tasks', task_filter
        )

        running_task = None
        for task in tasks:
            task_state = task['Status']['State']

            if task_state == 'running':
                self.log.debug(
                    "Task %s of Docker service %s status: %s",
                    task['ID'][:7],
                    self.service_id[:7],
                    pformat(task_state),
                )
                # there should be at most one running task
                running_task = task
            if task_state == 'rejected':
                task_err = task['Status']['State']['Err']
                self.log.error("Task {} of Docker service {} status {} "
                               "message {}"
                               .format(task['ID'][:7], self.service_id[:7],
                                       pformat(task_state), pformat(task_err)))
                # If the tasks is rejected -> remove it
                yield self.stop()

        if running_task is not None:
            return None
        else:
            return 0

    @gen.coroutine
    def get_service(self):
        self.log.debug("Getting Docker service '%s' with id: '%s'",
                       self.service_name, self.service_id)
        try:
            service = yield self.docker(
                'inspect_service', self.service_name
            )
            self.service_id = service['ID']
        except APIError as err:
            if err.response.status_code == 404:
                self.log.info("Docker service '%s' is gone", self.service_name)
                service = None
                # Docker service is gone, remove service id
                self.service_id = ''
            elif err.response.status_code == 500:
                self.log.info("Docker Swarm Server error")
                service = None
                # Docker service is unhealthy, remove the service_id
                self.service_id = ''
            else:
                raise
        return service

    @gen.coroutine
    def start(self):
        """Start the single-user server in a docker service.
        You can specify the params for the service through jupyterhub_config.py
        or using the user_options
        """

        # https://github.com/jupyterhub/jupyterhub/blob/master/jupyterhub/user.py#L202
        # By default jupyterhub calls the spawner passing user_options
        if self.use_user_options:
            user_options = self.user_options
        else:
            user_options = {}

        service = yield self.get_service()
        if service is None:
            if 'name' in user_options:
                self.server_name = user_options['name']

            if hasattr(self,
                       'container_spec') and self.container_spec is not None:
                container_spec = dict(**self.container_spec)
            elif user_options == {}:
                self.log.error("User: {} is trying to create a service "
                               "without a container_spec".format(
                                self.user.real_name))
                raise Exception("That notebook is missing a specification"
                                "to launch it, contact the admin to resolve "
                                "this issue")

            # If using rasmunk/sshfs mounts, ensure that the mig_mount
            # attributes is set
            for mount in self.container_spec['mounts']:
                if 'driver_config' in mount \
                        and 'rasmunk/sshfs' in mount['driver_config']:
                    if not hasattr(self.user, 'mig_mount') or \
                                    self.user.mig_mount is None:
                        self.log.error("User: {} missing mig_mount "
                                       "attribute".format(self.user.real_name))
                        raise Exception("Can't start that particular "
                                        "notebook image, missing MiG mount "
                                        "authentication keys, "
                                        "try reinitializing them "
                                        "through the MiG interface")
                    else:
                        # Validate required dictionary keys
                        required_keys = ['SESSIONID', 'USER_CERT',
                                         'TARGET_MOUNT_ADDR',
                                         'MOUNTSSHPRIVATEKEY',
                                         'MOUNTSSHPUBLICKEY']
                        missing_keys = [key for key in required_keys if key
                                        not in self.user.mig_mount]
                        if len(missing_keys) > 0:
                            self.log.error("User: {} missing mig_mount keys: {}"
                                           .format(self.user.real_name,
                                                   ",".join(missing_keys)))
                            raise Exception("MiG mount keys are available but "
                                            "missing the following items: {} "
                                            "try reinitialize them "
                                            "through the MiG interface"
                                            .format(",".join(missing_keys)))

            container_spec.update(user_options.get('container_spec', {}))
            # iterates over mounts to create
            # a new mounts list of docker.types.Mount
            container_spec['mounts'] = []
            for mount in self.container_spec['mounts']:
                m = dict(**mount)

                # Volume name
                if 'source' in m:
                    m['source'] = m['source'].format(
                        username=self.service_owner)
                    self.log.info("Volume name: " + m['source'])

                    # If a previous user volume is present, remove it
                    try:
                        yield self.docker('inspect_volume', m['source'])
                    except docker.errors.NotFound:
                        self.log.info("No volume named: " + m['source'])
                    else:
                        yield self.remove_volume(m['source'])

                # Custom volume
                if 'driver_config' in m:
                    if 'sshcmd' in m['driver_options']:
                        m['driver_options']['sshcmd'] = self.user.mig_mount[
                                                            'SESSIONID'] + \
                                                        self.user.mig_mount[
                                                            'TARGET_MOUNT_ADDR']

                    # If the id_rsa flag is present, set key
                    if 'id_rsa' in m['driver_options']:
                        m['driver_options']['id_rsa'] = self.user.mig_mount[
                            'MOUNTSSHPRIVATEKEY']

                    m['driver_config'] = docker.types.DriverConfig(
                        name=m['driver_config'], options=m['driver_options'])
                    del m['driver_options']

                container_spec['mounts'].append(docker.types.Mount(**m))

            # some Envs are required by the single-user-image
            container_spec['env'] = self.get_env()

            if hasattr(self, 'resource_spec'):
                resource_spec = self.resource_spec
            resource_spec.update(user_options.get('resource_spec', {}))

            if hasattr(self, 'networks'):
                networks = self.networks
            if user_options.get('networks') is not None:
                networks = user_options.get('networks')

            if hasattr(self, 'placement'):
                placement = self.placement
            if user_options.get('placement') is not None:
                placement = user_options.get('placement')

            image = container_spec['Image']
            del container_spec['Image']

            # create the service
            container_spec = docker.types.ContainerSpec(
                image, **container_spec)
            resources = docker.types.Resources(**resource_spec)

            task_spec = {'container_spec': container_spec,
                         'resources': resources,
                         'placement': placement
                         }
            task_tmpl = docker.types.TaskTemplate(**task_spec)
            resp = yield self.docker('create_service',
                                     task_tmpl,
                                     name=self.service_name,
                                     networks=networks)

            self.service_id = resp['ID']
            self.log.info("Created Docker service '%s' (id: %s) from image %s"
                          " for user %s", self.service_name,
                          self.service_id[:7], image, self.user.real_name)

        else:
            self.log.info(
                "Found existing Docker service '%s' (id: %s)",
                self.service_name, self.service_id[:7])
            # Handle re-using API token.
            # Get the API token from the environment variables
            # of the running service:
            envs = service['Spec']['TaskTemplate']['ContainerSpec']['Env']
            for line in envs:
                if line.startswith('JPY_API_TOKEN='):
                    self.api_token = line.split('=', 1)[1]
                    break

        ip = self.service_name
        port = self.service_port
        self.log.debug("Active service: '%s' with user '%s'",
                       self.service_name, self.user)

        # we use service_name instead of ip
        # https://docs.docker.com/engine/swarm/networking/#use-swarm-mode-service-discovery
        # service_port is actually equal to 8888
        return (ip, port)

    @gen.coroutine
    def removed_volume(self, name):
        result = False
        try:
            yield self.docker('remove_volume', name=name)
            self.log.info("Removed volume %s", name)
            result = True
        except APIError as err:
            if err.response.status_code == 409:
                self.log.info("Can't remove volume: %s yet", name),

        return result

    @gen.coroutine
    def remove_volume(self, name, max_attempts=15):
        attempt = 0
        removed = False
        # Volumes can only be removed after the service is gone
        while not removed:
            if attempt > max_attempts:
                self.log.info("Failed to remove volume %s", name)
                break
            self.log.info("Removing volume %s", name)
            removed = yield self.removed_volume(name=name)
            yield gen.sleep(1)
            attempt += 1

        return removed

    @gen.coroutine
    def stop(self, now=False):
        """Stop and remove the service

        Consider using stop/start when Docker adds support
        """
        self.log.info(
            "Stopping and removing Docker service %s (id: %s)",
            self.service_name, self.service_id[:7])

        service = yield self.get_service()
        if not service:
            self.log.warn("Docker service not found")
            return

        volumes = service['Spec']['TaskTemplate']['ContainerSpec']['Mounts']
        # Even though it returns the service is gone
        # the underlying containers are still being removed
        removed_service = yield self.docker('remove_service', service['ID'])
        if removed_service:
            self.log.info(
                "Docker service %s (id: %s) removed",
                self.service_name, self.service_id[:7])

            for volume in volumes:
                name = str(volume['Source'])
                yield self.remove_volume(name=name, max_attempts=15)

        self.clear_state()
