"""
A Spawner for JupyterHub that runs each user's
server in a separate Docker Service
"""

import ast
import copy
import docker
import hashlib
import html
from asyncio import sleep
from async_generator import async_generator, yield_
from textwrap import dedent
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from docker.errors import APIError
from docker.tls import TLSConfig
from docker.types import (
    TaskTemplate,
    ContainerSpec,
    DriverConfig,
    Resources,
    RestartPolicy,
    Placement,
)
from docker.utils import kwargs_from_env
from tornado import gen
from jupyterhub.spawner import Spawner
from traitlets import default, Dict, Unicode, List, Bool, Int, Any
from jhub.util import discover_datatype_klass


class UnicodeOrFalse(Unicode):
    info_text = "a unicode string or False"

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
    c.SwarmSpawner.images = [
        {'image': 'ucphhpc/base-notebook:latest',
        'name': 'Default jupyter notebook'}

    ]

    The images must be locally available before the user can spawn them
    """

    images = List(
        trait=Dict(),
        default_value=[
            {
                "image": "ucphhpc/base-notebook:latest",
                "name": "Default Jupyter Notebook",
            }
        ],
        minlen=1,
        help=dedent(
            """
            Docker images that are available to the user of the host.
        """
        ),
    ).tag(config=True)

    form_template = Unicode(
        """
        <label for="select_image">Select a notebook image:</label>
        <select class="form-control" name="select_image" required autofocus>
            {option_template}
        </select>""",
        help=dedent(
            """
            Form template.
        """
        ),
    ).tag(config=True)

    option_template = Unicode(
        """<option value="{value}">{name}</option>""",
        help=dedent(
            """
            Template for html form options.
        """
        ),
    ).tag(config=True)

    _executor = None

    @default("options_form")
    def _options_form(self):
        """Return the form with the drop-down menu."""
        template_options = []
        for image in self.images:
            value = dict(image=image["image"], name=image["name"])
            template_value = dict(name=image["name"], value=value)
            template_options.append(self.option_template.format(**template_value))
        option_template = "".join(template_options)
        return self.form_template.format(option_template=option_template)

    def options_from_form(self, form_data):
        """Parse the submitted form data and turn it into the correct
        structures for self.user_options."""
        self.log.debug(
            "User: {} submitted spawn form: {}".format(self.user.name, form_data)
        )

        # formdata format: {'select_image': [{'image': 'jupyterhub/singleuser',
        # 'id': "Basic Jupyter Notebook"}]}
        form_image_data = form_data.get("select_image", None)
        if not isinstance(form_image_data, list):
            self.log.error(
                "User: {} submitted an incorrect form, expected a list: {}".format(
                    self.user.name, form_image_data
                )
            )
            raise ValueError("An invalid form was submitted.")

        try:
            formatted_image_data = ast.literal_eval(form_image_data[0])
        except ValueError:
            self.log.error("Failed to literal_eval: {}".format(form_image_data[0]))
            raise ValueError("An invalid form was submitted.")

        if not isinstance(formatted_image_data, dict):
            self.log.error(
                "User: {} submitted an incorrect form, expected a dictionary: {}".format(
                    self.user.name, formatted_image_data
                )
            )
            raise ValueError("An invalid form was submitted.")
        image_configuration = formatted_image_data
        if "image" not in image_configuration:
            self.log.error("An 'image' tag was not in the image configuration")
            raise RuntimeError("An incorrect image configuration was supplied")

        if "name" not in image_configuration:
            self.log.error("An 'name' tag was not in the image configuration")
            raise RuntimeError("An incorrect image configuration was supplied")

        spawn_image_name = html.escape(image_configuration["name"])
        spawn_image_data = html.escape(image_configuration["image"])
        # Don't allow users to input their own images
        if spawn_image_name not in [image["name"] for image in self.images]:
            self.log.warn(
                "User: {} tried to spawn an invalid image: {}".format(
                    self.user.name, spawn_image_name
                )
            )
            raise RuntimeError(
                "An invalid image name was selected: {}".format(spawn_image_name)
            )

        if spawn_image_data not in [image["image"] for image in self.images]:
            self.log.warn(
                "User: {} tried to spawn an invalid image: {}".format(
                    self.user.name, spawn_image_data
                )
            )
            raise RuntimeError(
                "An invalid image was selected: {}".format(spawn_image_data)
            )

        options = {
            "spawn_image_name": spawn_image_name,
            "spawn_image_data": spawn_image_data,
        }
        return options

    @property
    def executor(self, max_workers=1):
        """single global executor"""
        cls = self.__class__
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(max_workers)
        return cls._executor

    _client = None

    _tasks = None

    @property
    def client(self):
        """single global client instance"""
        cls = self.__class__
        if cls._client is None:
            kwargs = {}
            if self.tls_config:
                kwargs["tls"] = TLSConfig(**self.tls_config)
            kwargs.update(kwargs_from_env())
            client = docker.APIClient(version="auto", **kwargs)

            cls._client = client
        return cls._client

    service_id = Unicode()

    service_port = Int(
        8888,
        min=1,
        max=65535,
        help=dedent(
            """
                The port on which the spawned service should listen.
            """
        ),
    ).tag(config=True)

    service_prefix = Unicode(
        "jupyter",
        help=dedent(
            """
                Prefix for service names. The full service name for a particular
                user will be <prefix>-<hash(username)>-<server_name>.
            """
        ),
    ).tag(config=True)

    tls_config = Dict(
        help=dedent(
            """Arguments to pass to docker TLS configuration.
            Check for more info:
            http://docker-py.readthedocs.io/en/stable/tls.html
            """
        ),
    ).tag(config=True)

    container_spec = Dict(
        {},
        help=dedent(
            """
            Params to create the service.
            """
        ),
    ).tag(config=True)

    log_driver = Dict(
        {},
        help=dedent(
            """
            Which logging driver should be used for each service.
            """
        ),
    ).tag(config=True)

    resources_spec = Dict(
        {},
        help=dedent(
            """
            Params about cpu and memory limits.
            """
        ),
    ).tag(config=True)

    placement_spec = Dict(
        {},
        help=dedent(
            """
            List of placement_spec constraints for all images.
            """
        ),
    ).tag(config=True)

    endpoint_spec = Dict(
        {},
        help=dedent(
            """
            Properties that can be configured to access and load balance a service.
            """
        ),
    ).tag(config=True)

    networks = List(
        [],
        help=dedent(
            """
            Additional args to create_host_config for service create.
            """
        ),
    ).tag(config=True)

    configs = List(
        trait=Dict(),
        help=dedent(
            """
            Configs to attach to the service.
            """
        ),
    ).tag(config=True)

    jupyterhub_service_name = Unicode(
        help=dedent(
            """
            Name of the service running the JupyterHub.
            """
        ),
    ).tag(config=True)

    user_format_attributes = List(
        default_value=[],
        traits=[Unicode()],
        allow_none=True,
        help=dedent(
            """
            List of JupyterHub user attributes that are used to format
            the service configuration before it is scheduled
            """
        ),
    ).tag(config=True)

    set_service_image_name_label = Bool(
        default_value=False,
        help=dedent(
            """
            Whether the selected image name should be set as a ContainerSpec label
            with the 'ImageName' key name. This can be used to identify the name of the image
            configuration that was used for the service.
            """
        ),
    ).tag(config=True)

    use_spawner_datatype_helpers = Bool(
        default_value=False,
        help=dedent(
            """
            Whether the spawner should use its own helper data types to
            validate whether the supplied configs are valid.
            The supported container spec data type helpers
            are declared in the `supported_spawner_datatype_helpers` attribute.
            """
        ),
    ).tag(config=True)

    supported_spawner_datatype_helpers = List(
        default_value=["mounts"],
        traits=[Unicode()],
        allow_none=True,
        help=dedent(
            """
            The supported container spec data types that 
            the spawner can help with instantiate and validate.
            """
        ),
    ).tag(config=True)

    # TODO, check if this can be merged with the JupyterHub
    # scopes access system introduced in 3.0
    enable_access_system = Bool(
        default_value=False,
        help=dedent(
            """
            Whether the SwarmSpawner Access System should be enabled.
            This can be used to restrict access to certain images to
            certain users.
            """
        ),
    ).tag(config=True)

    access_system = Any(
        default_value=None,
        allow_none=True,
        help=dedent(
            """
            The Access System type that is used to validate user permissions
            to spawn specific image types.
            """
        ),
    ).tag(config=True)

    enable_accelerator_system = Bool(
        default_value=False,
        help=dedent(
            """
            Whether the SwarmSpawner Accelerator system should be enabled.
            This system can be used to associate accelerators such as GPUs
            with a particular or multiple image configurations.
            """
        ),
    ).tag(config=True)

    accelerator_manager = Any(
        default_value=None,
        allow_none=True,
        help=dedent(
            """
            The Accelerator Manager that manages the requests and lifetime of the available
            set of Accelerator Pools.
            """
        ),
    ).tag(config=True)

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
            m.update(self.user.name.encode("utf-8"))
            if hasattr(self.user, "name"):
                # Maximum 63 characters, 10 are comes from the underlying format
                # i.e. prefix=jupyter-, postfix=-1
                # get up to last 32 characters as service identifier
                self._service_owner = self.user.name[-32:]
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

        return "{}-{}-{}".format(self.service_prefix, self.service_owner, server_name)

    @property
    def tasks(self):
        return self._tasks

    @tasks.setter
    def tasks(self, tasks):
        self._tasks = tasks

    def load_state(self, state):
        super().load_state(state)
        self.service_id = state.get("service_id", "")

    def get_state(self):
        state = super().get_state()
        if self.service_id:
            state["service_id"] = self.service_id
        return state

    def clear_state(self):
        super().clear_state()
        self.service_id = ""

    @staticmethod
    def _env_keep_default(param):
        """it's called in traitlets. It's a special method name.
        Don't inherit any env from the parent process.
        """
        return []

    def _public_hub_api_url(self):
        proto, path = self.hub.api_url.split("://", 1)
        _, rest = path.split(":", 1)
        return "{proto}://{name}:{rest}".format(
            proto=proto, name=self.jupyterhub_service_name, rest=rest
        )

    def get_env(self):
        env = super().get_env()
        env.update(
            dict(
                JPY_USER=self.user.name,
                JPY_COOKIE_NAME=self.user.server.cookie_name,
                JPY_BASE_URL=self.user.server.base_url,
                JPY_HUB_PREFIX=self.hub.server.base_url,
            )
        )

        env["JPY_HUB_API_URL"] = self._public_hub_api_url()
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
        self.log.debug(
            "Getting Docker service '{}' with id: '{}'".format(
                self.service_name, self.service_id
            )
        )
        try:
            service = yield self.docker("inspect_service", self.service_name)
            self.service_id = service["ID"]
        except APIError as err:
            if err.response.status_code == 404:
                self.log.info("Docker service '{}' is gone".format(self.service_name))
                service = None
                # Docker service is gone, remove service id
                self.service_id = ""
            elif err.response.status_code == 500:
                self.log.info("Docker Swarm Server error")
                service = None
                # Docker service is unhealthy, remove the service_id
                self.service_id = ""
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

        task_filter = {"service": service["Spec"]["Name"]}
        self.tasks = yield self.docker("tasks", task_filter)

        running_task = None
        for task in self.tasks:
            task_state = task["Status"]["State"]
            if task_state == "running":
                self.log.debug(
                    "Task {} of Docker service {} status: {}".format(
                        task["ID"][:7], self.service_id[:7], pformat(task_state)
                    ),
                )
                # there should be at most one running task
                running_task = task
            if task_state == "rejected":
                task_err = task["Status"]["Err"]
                self.log.error(
                    "Task {} of Docker service {} status {} "
                    "message {}".format(
                        task["ID"][:7],
                        self.service_id[:7],
                        pformat(task_state),
                        pformat(task_err),
                    )
                )
                # If the tasks is rejected -> remove it
                yield self.stop()

        if running_task is not None:
            return None
        else:
            return 0

    async def check_update(self, image, tag="latest"):
        full_image = "".join([image, ":", tag])
        download_tracking = {}
        initial_output = False
        total_download = 0
        for download in self.client.pull(image, tag=tag, stream=True, decode=True):
            if not initial_output:
                await yield_(
                    {
                        "progress": 70,
                        "message": "Downloading new update "
                        "for {}".format(full_image),
                    }
                )
                initial_output = True
            if "id" and "progress" in download:
                _id = download["id"]
                if _id not in download_tracking:
                    del download["id"]
                    download_tracking[_id] = download
                else:
                    download_tracking[_id].update(download)

                # Output every 20 MB
                for _id, tracker in download_tracking.items():
                    if (
                        tracker["progressDetail"]["current"]
                        == tracker["progressDetail"]["total"]
                    ):
                        total_download += tracker["progressDetail"]["total"] * pow(
                            10, -6
                        )
                        await yield_(
                            {
                                "progress": 80,
                                "message": "Downloaded {} MB of {}".format(
                                    total_download, full_image
                                ),
                            }
                        )
                        # return to web processing
                        await sleep(1)

                # Remove completed
                download_tracking = {
                    _id: tracker
                    for _id, tracker in download_tracking.items()
                    if tracker["progressDetail"]["current"]
                    != tracker["progressDetail"]["total"]
                }

    @async_generator
    async def progress(self):
        if self.tasks:
            top_task = self.tasks[0]
            image = top_task["Spec"]["ContainerSpec"]["Image"]
            self.log.info("Spawning progress of {} with image".format(self.service_id))
            task_status = top_task["Status"]["State"]
            _tag = None
            if ":" in image:
                _image, _tag = image.split(":")
            else:
                _image = image
            if task_status == "preparing":
                await yield_(
                    {
                        "progress": 50,
                        "message": "Preparing a server "
                        "with {} the image".format(image),
                    }
                )
                await yield_(
                    {
                        "progress": 60,
                        "message": "Checking for new version of {}".format(image),
                    }
                )
                if _tag is not None:
                    await self.check_update(_image, _tag)
                else:
                    await self.check_update(_image)
                self.log.info("Finished progress from spawning {}".format(image))

    @gen.coroutine
    def removed_volume(self, name):
        result = False
        try:
            yield self.docker("remove_volume", name=name)
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
        self.log.debug("User: {}, start spawn".format(self.user.name))
        if not self.user_options:
            self.log.error("No user_options from the JupyterHub form has been set")
            raise RuntimeError(
                "No user options were received from the JupyterHub Spawn form"
            )
        user_options = self.user_options
        self.log.debug("User options received: {}".format(user_options))

        service = yield self.get_service()
        if service is None:
            # Setup the global default state
            # As defined by:
            # https://docker-py.readthedocs.io/en/stable/api.html#docker.types.TaskTemplate
            new_service_config = {
                "container_spec": {
                    "command": None,
                    "args": None,
                    "hostname": None,
                    "env": None,
                    "workdir": None,
                    "user": None,
                    "labels": None,
                    "mounts": None,
                    "stop_grace_period": None,
                    "secrets": None,
                    "tty": None,
                    "groups": None,
                    "open_stdin": None,
                    "read_only": None,
                    "stop_signal": None,
                    "healthcheck": None,
                    "hosts": None,
                    "dns_config": None,
                    "configs": None,
                    "privileges": None,
                    "isolation": None,
                    "init": None,
                    "cap_add": None,
                    "cap_drop": None,
                    "sysctls": None,
                },
                "resources": None,
                "restart_policy": None,
                "placement": None,
                "log_driver": None,
                "networks": None,
                "force_update": None,
            }

            self.log.debug("Starting new service config: {}".format(new_service_config))
            # Set the default value for each attribute
            for key, value in new_service_config.items():
                if hasattr(self, key) and getattr(self, key):
                    new_service_config[key] = getattr(self, key)
                if key in user_options and user_options[key]:
                    new_service_config[key] = user_options[key]
            self.log.debug(
                "Starting spawn of user: {} with the service config: {}".format(
                    self.user.name, new_service_config
                )
            )

            # Pass on the JupyterHub environment variables
            if not new_service_config["container_spec"]["env"]:
                new_service_config["container_spec"]["env"] = {}
            new_service_config["container_spec"]["env"].update(self.get_env())

            # Prepare the attributes that can be used to format the new_service_config
            # before we proceed
            user_format_dict = {}
            if self.user_format_attributes:
                for attr in self.user_format_attributes:
                    if hasattr(self.user, attr):
                        value = getattr(self.user, attr)
                        if not isinstance(value, dict):
                            value = {attr: value}
                        user_format_dict[attr] = value
                self.log.debug(
                    "Spawner user_format_attributes prepared: {}".format(
                        user_format_dict
                    )
                )

            if "spawn_image_name" not in user_options:
                self.log.error(
                    "No 'spawn_image_name' was found in the user_options: {}".format(
                        user_options
                    )
                )
                raise RuntimeError("Missing image data to start the requested server")

            if "spawn_image_data" not in user_options:
                self.log.error(
                    "No 'spawn_image_data' was found in the user_options: {}".format(
                        user_options
                    )
                )
                raise RuntimeError("Missing image data to start the requested server")

            # Which image to spawn
            spawn_image_name = user_options["spawn_image_name"]
            spawn_image_data = user_options["spawn_image_data"]
            selected_image_configuration = None
            for image in self.images:
                if (
                    spawn_image_name == image["name"]
                    and spawn_image_data == image["image"]
                ):
                    selected_image_configuration = copy.deepcopy(image)

            if not selected_image_configuration:
                self.log.error(
                    "Failed to find an image configuration that matched what the user had selected"
                )
                raise RuntimeError(
                    "Failed to find the specified image in the JupyterHub image configuration"
                )
            self.log.debug(
                "User has requested the image configuration: {}".format(
                    selected_image_configuration
                )
            )

            if self.enable_access_system:
                self.log.debug(
                    "Access system enabled, checking permissions for: {}".format(
                        selected_image_configuration
                    )
                )
                if self.access_system.restricted(selected_image_configuration):
                    allowed = self.access_system.allowed(
                        self.user.name, selected_image_configuration
                    )
                    if not allowed:
                        raise PermissionError(
                            "Access to that Notebook is restricted, you don't currently have permission to access it"
                        )
                        # TODO, add possible contact info about resolving the issue

            # Update the new service config with the selected image configuration
            for attr, value in selected_image_configuration.items():
                if attr in new_service_config["container_spec"]:
                    # If not set, just set the value
                    if not new_service_config["container_spec"][attr]:
                        new_service_config["container_spec"][attr] = value
                    # If the attribute is a dictionary, merge the two dicts
                    if new_service_config["container_spec"][attr] and isinstance(
                        new_service_config["container_spec"][attr], dict
                    ):
                        new_service_config["container_spec"][attr].update(**value)

            if self.set_service_image_name_label:
                self.log.debug(
                    "Spawner set_service_image_name_label is enabled, updating container_spec labels"
                )
                if not new_service_config["container_spec"]["labels"]:
                    new_service_config["container_spec"]["labels"] = {}
                new_service_config["container_spec"]["labels"].update(
                    {"ImageName": selected_image_configuration["name"]}
                )

            if self.use_spawner_datatype_helpers:
                self.log.debug(
                    "Spawner use_spawner_datatype_helpers enabled, checking supported spawner data types: {}".format(
                        self.supported_spawner_datatype_helpers
                    )
                )
                # Check for special new service config attributes that required
                # custom Data Types
                for attr in self.supported_spawner_datatype_helpers:
                    if attr in new_service_config["container_spec"]:
                        # Deep copy the existing config, because it will
                        # be overriden
                        config = copy.deepcopy(
                            new_service_config["container_spec"][attr]
                        )
                        if isinstance(config, (list, set, tuple)):
                            new_datatypes = []
                            for c in config:
                                datatype_klass = discover_datatype_klass(attr, c)
                                instance = datatype_klass(c)
                                # TODO, add the ability to pass user_format_attributes
                                new_datatype = yield instance.create(**user_format_dict)
                                new_datatypes.append(new_datatype)
                            new_service_config["container_spec"][attr] = new_datatypes
                        else:
                            datatype_klass = discover_datatype_klass(attr, config)
                            instance = datatype_klass(config)
                            # TODO, add the ability to pass user_format_attributes
                            new_datatype = yield instance.create(**user_format_dict)
                            new_service_config["container_spec"][attr] = new_datatype

                        self.log.debug(
                            "Generated new datatypes: {}".format(
                                new_service_config["container_spec"][attr]
                            )
                        )

            if self.enable_accelerator_system:
                self.log.debug(
                    "Spawner enable_accelerator_system enabled, checking if any accelerator should be associated with the to be spawned session"
                )
                # Check if the image has requested a Pool
                if "accelerator_pools" in selected_image_configuration:
                    for pool in selected_image_configuration["accelerator_pools"]:
                        self.log.debug("Looking for accelerator pool: {}".format(pool))
                        # If the user already has a request accelerator, release it first
                        # before requesting a new one
                        requested_accelerator = self.accelerator_manager.request(pool, self.user.name)
                        self.log.debug(
                            "Spawner tried to acquire accelerator resource from pool: {} - result: {}".format(pool, requested_accelerator)
                        )
                        if requested_accelerator:
                            self.log.debug("Found requested acceelertor: {}".format(requested_accelerator))
                        else:
                            self.log.error("Failed to get request accelerator resource from pool: {} - result: {}".format(pool, requested_accelerator))

            # Create the service
            container_spec_kwargs = new_service_config.pop("container_spec")
            task_template_kwargs = {
                "container_spec": ContainerSpec(
                    selected_image_configuration["image"], **container_spec_kwargs
                )
            }

            for key, value in new_service_config.items():
                if key == "log_driver" and value:
                    task_template_kwargs[key] = DriverConfig(**value)
                if key == "resources" and value:
                    task_template_kwargs[key] = Resources(**value)
                if key == "restart_policy" and value:
                    task_template_kwargs[key] = RestartPolicy(**value)
                if key == "placement" and value:
                    task_template_kwargs[key] = Placement(**value)
                if key == "networks" and value or key == "force_update" and value:
                    # Either just a list of ids or an int
                    # https://docker-py.readthedocs.io/en/stable/api.html#docker.types.TaskTemplate
                    task_template_kwargs[key] = value

            task_template = TaskTemplate(**task_template_kwargs)
            self.log.debug("scheduling task template: {}".format(task_template))
            resp = yield self.docker(
                "create_service",
                task_template,
                name=self.service_name,
                networks=new_service_config["networks"],
            )

            self.service_id = resp["ID"]
            self.log.info(
                "Created Docker service {} (id: {}) from image {}"
                " for user {}".format(
                    self.service_name,
                    self.service_id[:7],
                    selected_image_configuration["image"],
                    self.user.name,
                )
            )
            yield self.wait_for_running_tasks()
        else:
            self.log.info(
                "Found existing Docker service '{}' (id: {})".format(
                    self.service_name, self.service_id[:7]
                )
            )
            # Handle re-using API token.
            # Get the API token from the environment variables
            # of the running service:
            envs = service["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"]
            for line in envs:
                if line.startswith("JPY_API_TOKEN="):
                    self.api_token = line.split("=", 1)[1]
                    break

        ip = self.service_name
        port = self.service_port
        self.log.debug(
            "Active service: '{}' with user '{}'".format(self.service_name, self.user)
        )

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
                self.service_name, self.service_id[:7]
            )
        )

        service = yield self.get_service()
        if not service:
            self.log.warn("Docker service not found")
            return

        # lookup mounts before removing the service
        volumes = None
        if "Mounts" in service["Spec"]["TaskTemplate"]["ContainerSpec"]:
            volumes = service["Spec"]["TaskTemplate"]["ContainerSpec"]["Mounts"]

        # Even though it returns the service is gone
        # the underlying containers are still being removed
        removed_service = yield self.docker("remove_service", service["ID"])
        if removed_service:
            self.log.info(
                "Docker service {} (id: {}) removed".format(
                    self.service_name, self.service_id[:7]
                )
            )
            if volumes is not None:
                for volume in volumes:
                    labels = volume.get("VolumeOptions", {}).get("Labels", {})
                    # Whether the volume should be kept
                    if "autoremove" in labels and labels["autoremove"] != "False":
                        self.log.debug("Volume {} is not kept".format(volume))
                        if "Source" in volume:
                            # Validate the volume exists
                            try:
                                yield self.docker("inspect_volume", volume["Source"])
                            except docker.errors.NotFound:
                                self.log.info("No volume named: " + volume["Source"])
                            else:
                                yield self.remove_volume(volume["Source"])
                        else:
                            self.log.error(
                                "Volume {} didn't have a 'Source' key so it "
                                "can't be removed".format(volume)
                            )

    @gen.coroutine
    def wait_for_running_tasks(self, max_attempts=20):
        preparing, running = False, False
        attempt = 0
        while not running:
            service = yield self.get_service()
            task_filter = {"service": service["Spec"]["Name"]}
            self.tasks = yield self.docker("tasks", task_filter)
            preparing = False
            for task in self.tasks:
                task_state = task["Status"]["State"]
                self.log.info(
                    "Waiting for service: {} current task status: {}".format(
                        service["ID"], task_state
                    )
                )
                if task_state == "running":
                    running = True
                if task_state == "preparing":
                    preparing = True
                if task_state == "rejected" or attempt > max_attempts:
                    return False
            if not preparing:
                attempt += 1
            yield gen.sleep(1)
