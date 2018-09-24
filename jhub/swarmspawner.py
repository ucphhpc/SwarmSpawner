"""
A Spawner for JupyterHub that runs each user's
server in a separate Docker Service
"""

import hashlib
import docker
import copy
from asyncio import sleep
from async_generator import async_generator, yield_
from textwrap import dedent
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from docker.errors import APIError
from docker.tls import TLSConfig
from docker.types import TaskTemplate, Resources, ContainerSpec, Placement
from docker.utils import kwargs_from_env
from tornado import gen
from jupyterhub.spawner import Spawner
from traitlets import (
    default,
    Dict,
    Unicode,
    List,
    Bool,
    Int
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

    c.JupyterHub.spawner_class = 'jhub.SwarmSpawner'
    # Available docker images the user can spawn
    c.SwarmSpawner.dockerimages = [
        {'image': 'jupyterhub/singleuser:0.8.1',
        'name': 'Default jupyterhub singleuser notebook'}

    ]

    The images must be locally available before the user can spawn them
    """

    dockerimages = List(
        trait=Dict(),
        default_value=[{'image': 'jupyterhub/singleuser:0.8.1',
                        'name': 'Default jupyterhub singleuser notebook'}],
        minlen=1,
        config=True,
        help="Docker images that are available to the user of the host"
    )

    form_template = Unicode("""
        <label for="dockerimage">Select a notebook image:</label>
        <select class="form-control" name="dockerimage" required autofocus>
            {option_template}
        </select>""", config=True, help="Form template.")

    option_template = Unicode("""
        <option value="{image}">{name}</option>""",
                              config=True,
                              help="Template for html form options.")
    _executor = None

    disabled_form = Unicode()

    @default('options_form')
    def _options_form(self):
        """Return the form with the drop-down menu."""
        # User options not enabled -> return default jupyterhub form
        if not self.use_user_options:
            return self.disabled_form

        # Support the use of dynamic string replacement
        if hasattr(self.user, 'mount'):
            for di in self.dockerimages:
                if '{replace_me}' in di['name']:
                    di['name'] = di['name'].replace('{replace_me}',
                                                    self.user.mount[
                                                        'HOST'])
        options = ''.join([
            self.option_template.format(image=di['image'], name=di['name'])
            for di in self.dockerimages
        ])
        return self.form_template.format(option_template=options)

    def options_from_form(self, form_data):
        """Parse the submitted form data and turn it into the correct
           structures for self.user_options."""
        # user options not enabled, just return input
        if not self.use_user_options:
            return form_data

        i_default = self.dockerimages[0]
        # formdata looks like {'dockerimage': ['jupyterhub/singleuser']}"""
        image = form_data.get('dockerimage', [i_default])[0]
        # Don't allow users to input their own images
        if image not in [image['image'] for image in self.dockerimages]:
            image = i_default
        options = {'user_selected_image': image}
        return options

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
                kwargs['tls'] = TLSConfig(**self.tls_config)
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
            Check for more info:
            http://docker-py.readthedocs.io/en/stable/tls.html
            """
        )
    )

    container_spec = Dict({}, config=True, help="Params to create the service")
    resource_spec = Dict(
        {}, config=True, help="Params about cpu and memory limits")

    placement = Dict({}, config=True,
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
            if hasattr(self.user, 'real_name'):
                self._service_owner = self.user.real_name[-39:]
            elif hasattr(self.user, 'name'):
                # Maximum 63 characters, 10 are comes from the underlying format
                # i.e. prefix=jupyter-, postfix=-1
                # get up to last 40 characters as service identifier
                self._service_owner = self.user.name[-39:]
            else:
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

    @property
    def tasks(self):
        return self._tasks

    @tasks.setter
    def tasks(self, tasks):
        self._tasks = tasks

    def load_state(self, state):
        super().load_state(state)
        self.service_id = state.get('service_id', '')

    def get_state(self):
        state = super().get_state()
        if self.service_id:
            state['service_id'] = self.service_id
        return state

    def clear_state(self):
        super().clear_state()
        self.service_id = ''

    @staticmethod
    def _env_keep_default():
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
    def get_service(self):
        self.log.debug("Getting Docker service '{}' with id: '{}'".format(
            self.service_name, self.service_id))
        try:
            service = yield self.docker(
                'inspect_service', self.service_name
            )
            self.service_id = service['ID']
        except APIError as err:
            if err.response.status_code == 404:
                self.log.info(
                    "Docker service '{}' is gone".format(self.service_name))
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
    def poll(self):
        """Check for a task state like `docker service ps id`"""
        service = yield self.get_service()
        if service is None:
            self.log.warn("Docker service not found")
            return 0

        task_filter = {'service': service['Spec']['Name']}
        self.tasks = yield self.docker(
            'tasks', task_filter
        )

        running_task = None
        for task in self.tasks:
            task_state = task['Status']['State']
            if task_state == 'running':
                self.log.debug(
                    "Task {} of Docker service {} status: {}".format(
                        task['ID'][:7], self.service_id[:7],
                        pformat(task_state)),
                )
                # there should be at most one running task
                running_task = task
            if task_state == 'rejected':
                task_err = task['Status']['Err']
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

    async def check_update(self, image, tag):
        full_image = ''.join([image, ':', tag])
        download_tracking = {}
        initial_output = False
        total_download = 0
        for download in self.client.pull(image, tag=tag, stream=True,
                                         decode=True):
            if not initial_output:
                await yield_(
                    {'progress': 70, 'message': 'Downloading new update '
                                                'for {}'.format(full_image)})
                initial_output = True
            if 'id' and 'progress' in download:
                _id = download['id']
                if _id not in download_tracking:
                    del download['id']
                    download_tracking[_id] = download
                else:
                    download_tracking[_id].update(download)

                # Output every 20 MB
                for _id, tracker in download_tracking.items():
                    if tracker['progressDetail']['current'] \
                            == tracker['progressDetail']['total']:
                        total_download += (tracker['progressDetail']['total'] *
                                           pow(10, -6))
                        await yield_({'progress': 80,
                                      'message': 'Downloaded {} MB of {}'
                                     .format(total_download, full_image)})
                        # return to web processing
                        await sleep(1)

                # Remove completed
                download_tracking = {_id: tracker for _id, tracker in
                                     download_tracking.items() if
                                     tracker['progressDetail']['current'] !=
                                     tracker[
                                         'progressDetail']['total']}

    @async_generator
    async def progress(self):
        top_task = self.tasks[0]
        image = top_task['Spec']['ContainerSpec']['Image']
        self.log.info(
            "Spawning progress of {} with image".format(self.service_id))
        task_status = top_task['Status']['State']
        _image, _tag = image.split(":")
        if task_status == 'preparing':
            await yield_({'progress': 50,
                          'message': 'Preparing a server '
                                     'with {} the image'.format(image)})
            await yield_({'progress': 60,
                          'message': 'Checking for new version of {}'.format(
                              image)})
            await self.check_update(_image, _tag)
            self.log.info("Finished progress from spawning {}".format(image))

    @gen.coroutine
    def removed_volume(self, name):
        result = False
        try:
            yield self.docker('remove_volume', name=name)
            self.log.info("Removed volume: {}".format(name))
            result = True
        except APIError as err:
            if err.response.status_code == 409:
                self.log.info("Can't remove volume: {} yet".format(name)),

        return result

    @gen.coroutine
    def remove_volume(self, name, max_attempts=15):
        attempt = 0
        removed = False
        # Volumes can only be removed after the service is gone
        while not removed:
            if attempt > max_attempts:
                self.log.info("Failed to remove volume {}".format(name))
                break
            self.log.info("Removing volume {}".format(name))
            removed = yield self.removed_volume(name=name)
            yield gen.sleep(1)
            attempt += 1

        return removed

    @gen.coroutine
    def start(self):
        """Start the single-user server in a docker service.
        You can specify the params for the service through
        jupyterhub_config.py or using the user_options
        """
        self.log.info("User: {}, start spawn".format(self.user.__dict__))

        # https://github.com/jupyterhub/jupyterhub
        # /blob/master/jupyterhub/user.py#L202
        # By default jupyterhub calls the spawner passing user_options
        if self.use_user_options:
            user_options = self.user_options
        else:
            user_options = {}

        service = yield self.get_service()
        if service is None:
            # Validate state
            if hasattr(self, 'container_spec') \
                    and self.container_spec is not None:
                container_spec = dict(**self.container_spec)
            elif user_options == {}:
                self.log.error(
                    "User: {} is trying to create a service"
                    " without a container_spec".format(self.user))
                raise Exception("That notebook is missing a specification"
                                "to launch it, contact the admin to resolve "
                                "this issue")

            # Setup service
            container_spec.update(user_options.get('container_spec', {}))

            # Which image to spawn
            if self.use_user_options and 'user_selected_image' in user_options:
                uimage = user_options['user_selected_image']
                image_info = None
                for di in self.dockerimages:
                    if di['image'] == uimage:
                        image_info = copy.deepcopy(di)
                if image_info is None:
                    err_msg = "User selected image: {} couldn't be found" \
                        .format(uimage['image'])
                    self.log.error(err_msg)
                    raise Exception(err_msg)
            else:
                # Default image
                image_info = self.dockerimages[0]

            self.log.debug("Image info: {}".format(image_info))
            # Does that image have restricted access
            if 'access' in image_info and self.service_owner not in image_info['access']:
                    self.log.error("User: {} tried to launch {} without access".format(
                        self.service_owner, image_info['image']
                    ))
                    raise Exception("You don't have permission to launch that image")

            # Does the selected image have mounts associated
            container_spec['mounts'] = []
            mounts = []
            if 'mounts' in image_info:
                mounts = image_info['mounts']

            for mount in mounts:
                # Expects a mount_class that supports 'create'
                if hasattr(self.user, 'data'):
                    m = yield mount.create(self.user.data, owner=self.service_owner)
                else:
                    m = yield mount.create(owner=self.service_owner)
                container_spec['mounts'].append(m)

            # Some envs are required by the single-user-image
            if 'env' in container_spec:
                container_spec['env'].update(self.get_env())
            else:
                container_spec['env'] = self.get_env()

            # Log mounts config
            self.log.debug("User: {} container_spec mounts: {}".format(
                self.user, container_spec['mounts']))

            resource_spec = {}
            if hasattr(self, 'resource_spec'):
                resource_spec = self.resource_spec
            resource_spec.update(user_options.get('resource_spec', {}))

            networks = None
            if hasattr(self, 'networks'):
                networks = self.networks
            if user_options.get('networks') is not None:
                networks = user_options.get('networks')

            # Global placement
            placement = None
            if hasattr(self, 'placement'):
                placement = self.placement
            if user_options.get('placement') is not None:
                placement = user_options.get('placement')

            # Image to spawn
            image = image_info['image']

            # Placement of image
            if 'placement' in image_info:
                placement = image_info['placement']

            # Create the service
            container_spec = ContainerSpec(image, **container_spec)
            resources = Resources(**resource_spec)
            placement = Placement(**placement)

            task_spec = {'container_spec': container_spec,
                         'resources': resources,
                         'placement': placement
                         }
            task_tmpl = TaskTemplate(**task_spec)
            self.log.info("task temp: {}".format(task_tmpl))
            resp = yield self.docker('create_service',
                                     task_tmpl,
                                     name=self.service_name,
                                     networks=networks)
            self.service_id = resp['ID']
            self.log.info("Created Docker service {} (id: {}) from image {}"
                          " for user {}".format(self.service_name,
                                                self.service_id[:7], image,
                                                self.user))

            yield self.wait_for_running_tasks()

        else:
            self.log.info(
                "Found existing Docker service '{}' (id: {})".format(
                    self.service_name, self.service_id[:7]))
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
        self.log.debug("Active service: '{}' with user '{}'".format(
            self.service_name, self.user))

        # we use service_name instead of ip
        # https://docs.docker.com/engine/swarm/networking/#use-swarm-mode-service-discovery
        # service_port is actually equal to 8888
        return ip, port

    @gen.coroutine
    def stop(self, now=False):
        """Stop and remove the service
        Consider using stop/start when Docker adds support
        """
        self.log.info(
            "Stopping and removing Docker service {} (id: {})".format(
                self.service_name, self.service_id[:7]))

        service = yield self.get_service()
        if not service:
            self.log.warn("Docker service not found")
            return

        # lookup mounts before removing the service
        volumes = None
        if 'Mounts' in service['Spec']['TaskTemplate']['ContainerSpec']:
            volumes = service['Spec']['TaskTemplate']['ContainerSpec'][
                'Mounts']
        # Even though it returns the service is gone
        # the underlying containers are still being removed
        removed_service = yield self.docker('remove_service', service['ID'])
        if removed_service:
            self.log.info("Docker service {} (id: {}) removed".format(
                self.service_name, self.service_id[:7]))
            if volumes is not None:
                for volume in volumes:
                    if 'Source' in volume:
                        # Validate the volume exists
                        try:
                            yield self.docker('inspect_volume',
                                              volume['Source'])
                        except docker.errors.NotFound:
                            self.log.info(
                                "No volume named: " + volume['Source'])
                        else:
                            yield self.remove_volume(volume['Source'])

    @gen.coroutine
    def wait_for_running_tasks(self):
        running = False
        while not running:
            service = yield self.get_service()
            task_filter = {'service': service['Spec']['Name']}
            self.tasks = yield self.docker(
                'tasks', task_filter
            )
            for task in self.tasks:
                task_state = task['Status']['State']
                self.log.info("Waiting for service: {} current task status: {}"
                              .format(service['ID'], task_state))
                if task_state == 'running':
                    running = True
                if task_state == 'rejected':
                    return False
            yield gen.sleep(1)
