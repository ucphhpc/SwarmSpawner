"""
A Spawner for JupyterHub that runs each user's
server in a separate Docker Service
"""

import ast
import copy
import docker
import hashlib
import os
from asyncio import sleep
from async_generator import async_generator, yield_
from textwrap import dedent
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from docker.errors import APIError
from docker.tls import TLSConfig
from docker.types import (
    TaskTemplate,
    Resources,
    ContainerSpec,
    DriverConfig,
    Placement,
    ConfigReference,
    EndpointSpec,
)
from docker.utils import kwargs_from_env
from jupyterhub.spawner import Spawner
from traitlets import default, Dict, Unicode, List, Bool, Int
from jhub.mount import VolumeMounter
from jhub.util import recursive_format


def get_user_uid_gid(dictionary, delimiter=":"):
    uid_gid = dictionary.get("uid_gid", {})
    if not uid_gid:
        return None, None

    if delimiter not in uid_gid:
        return None, None

    uid, gid = uid_gid.split(delimiter)
    return uid, gid


def prepare_user_config_reference(
    config_id, config_name, filename=None, uid=1000, gid=1000
):
    """Create a user config with a file associated with it"""
    return dict(
        config_id=config_id,
        config_name=config_name,
        filename=filename,
        uid=uid,
        gid=gid,
    )


def get_docker_client(api_client_kwargs=None, tls_kwargs=None):
    if not api_client_kwargs:
        api_client_kwargs = {}
    if not tls_kwargs:
        tls_kwargs = {}

    kwargs = {}
    if api_client_kwargs:
        kwargs.update(api_client_kwargs)

    if tls_kwargs:
        kwargs["tls"] = TLSConfig(**tls_kwargs)

    kwargs.update(kwargs_from_env())
    return docker.APIClient(version="auto", **kwargs)


def run_docker(method_name, *args, **kwargs):
    client = get_docker_client()
    docker_method = get_instance_function(client, method_name)
    if not docker_method:
        return False
    return run_with_executor(docker_method, *args, **kwargs).result()


def get_config(config_name_or_id):
    try:
        found = run_docker("inspect_config", config_name_or_id)
        return True, found
    except docker.errors.NotFound:
        return False, "Docker config: {} does not exist".format(config_name_or_id)
    return False, "Unknown error for finding the config"


def prune_config(config_name_or_id):
    try:
        removed = run_docker("remove_config", config_name_or_id)
        return True, removed
    except docker.errors.NotFound:
        return False, "Can't remove config: {} because it does not exist".format(
            config_name_or_id
        )
    return False, "Failed to remove config: {}, unknown error".format(config_name_or_id)


def remove_volume(name):
    try:
        run_docker("remove_volume", name=name)
        return True, "removed volume: {}".format(name)
    except APIError as err:
        if err.response.status_code == 409:
            return False, "Failed to remove volume: {}".format(name)
    return False, "Unknown error occured while removing volume: {}".format(name)


def run_with_executor(func, *args, **kwargs):
    """Run a function in a thread pool executor"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(func, *args, **kwargs)


def get_instance_function(instance, func_name):
    if hasattr(instance, func_name):
        return getattr(instance, func_name)
    return None


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
            Option template for value and name options when rendering the form_template
            """
        ),
    ).tag(config=True)

    user_upload_form = Unicode(
        """
        <div class="upload-form" style="padding-top: 2em;">
            <div class="form-group">
                <label for="user-upload">Optional Upload Install File (requirements.txt)</label>
                <input type="file" name="user-upload" id="user-upload" accept=".txt,.yml" class="form-control"/>
            </div>
        </div>
        """,
        help=dedent(
            """ Form for allowing user upload of install files that can be used to prepare the
            specified environment.
            """
        ),
    ).tag(config=True)

    enable_user_upload_install_files = Bool(
        False,
        help=dedent(
            """
            Allow users to upload install files that can be used to prepare the requsted environment.
            """
        ),
    ).tag(config=True)

    allowed_user_upload_extensions = List(
        trait=Unicode(),
        default_value=[".txt"],
        help=dedent(
            """
            Allowed file extensions for user upload of install files
            """
        ),
    ).tag(config=True)

    user_upload_destination_directory = Unicode(
        os.path.join(os.sep, "user-installs"),
        help=dedent(
            """
            Directory where user install files will be stored inside the spawned container.
        """
        ),
    ).tag(config=True)

    @default("options_form")
    def _options_form(self):
        """Return the form with the drop-down menu."""
        # User options not enabled -> return default jupyterhub form
        if not self.use_user_options:
            return ""
        template_options = []
        for di in self.images:
            value = dict(image=di["image"], name=di["name"])
            template_value = dict(name=di["name"], value=value)
            template_options.append(self.option_template.format(**template_value))
        option_template = "".join(template_options)
        user_form = self.form_template.format(option_template=option_template)
        if self.enable_user_upload_install_files:
            user_form += self.user_upload_form
        return user_form

    def options_from_form(self, form_data):
        """Parse the submitted form data and turn it into the correct
        structures for self.user_options."""
        # user options not enabled, just return input
        if not self.use_user_options:
            return form_data

        self.log.debug(
            "User: {} submitted spawn form: {}".format(self.user.name, form_data)
        )
        # formdata format: {'select_image': {'image': 'jupyterhub/singleuser',
        # 'id': "Basic Jupyter Notebook"}}
        image_data = form_data.get("select_image", None)
        if not image_data:
            image_data = self.images[0]
        else:
            if len(image_data) > 1:
                self.log.warn(
                    "User: {} tried to spawn multiple images".format(self.user.name)
                )
                raise RuntimeError("You can only select 1 image to spawn")
            image_data = ast.literal_eval(image_data[0])

        if "image" not in image_data or "name" not in image_data:
            self.log.error(
                "Either image or name was not in the supplied "
                "form's image data: {}".format(image_data)
            )
            raise RuntimeError("An incorrect image form was supplied")

        selected_name = image_data["name"]
        selected_image = image_data["image"]
        if selected_name not in [image["name"] for image in self.images]:
            self.log.warn(
                "User: {} tried to spawn an invalid image: {}".format(
                    self.user.name, selected_name
                )
            )
            raise RuntimeError(
                "An invalid image name was selected: {}".format(selected_name)
            )

        if selected_image not in [image["image"] for image in self.images]:
            self.log.warn(
                "User: {} tried to spawn an invalid image: {}".format(
                    self.user.name, selected_image
                )
            )
            raise RuntimeError(
                "An invalid image was selected: {}".format(selected_image)
            )

        # Don't allow users to input their own images
        options = {
            "user_selected_name": selected_name,
            "user_selected_image": selected_image,
        }

        # Whether user upload install files form should be parsed
        if self.enable_user_upload_install_files:
            # Check for uploaded file
            user_uploaded_content = form_data.get("user-upload_file", [])
            self.log.debug(
                "Processing user uploaded content {}".format(user_uploaded_content)
            )
            user_install_files = []
            for upload_file in user_uploaded_content:
                if "filename" in upload_file and "body" in upload_file:
                    filename = upload_file.get("filename", None)
                    if "." not in filename:
                        self.log.error(
                            "User: {} tried to upload an invalid file: {}".format(
                                self.user.name, filename
                            )
                        )
                        raise RuntimeError(
                            "An invalid file was uploaded, missing a valid extension, the allowed ones are: {}".format(
                                " ".join(self.allowed_user_upload_extensions)
                            )
                        )

                    # Allow for multiple extensions
                    name, extension = (
                        ".".join(filename.split(".")[:-1]),
                        ".{}".format(filename.split(".")[-1]),
                    )
                    if extension not in self.allowed_user_upload_extensions:
                        self.log.error(
                            "User: {} upload filename extension {} was not in the allowed set of: {}".format(
                                self.user.name,
                                extension,
                                self.allowed_user_upload_extensions,
                            )
                        )
                        raise RuntimeError(
                            "An invalid file extension used, the allowed ones are: {}".format(
                                " ".join(self.allowed_user_upload_extensions)
                            )
                        )
                    user_install_files.append(
                        {
                            "name": name,
                            "extension": extension,
                            "data": upload_file.get("body", None),
                        }
                    )
            options["user_install_files"] = user_install_files
        self.log.debug("Options from form {}".format(options))
        return options

    _client = None

    @property
    def client(self):
        """single global client instance"""
        cls = self.__class__

        if cls._client is None:
            cls._client = get_docker_client()
        return cls._client

    _tasks = None

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

    resource_spec = Dict(
        {},
        help=dedent(
            """
            Params about cpu and memory limits.
            """
        ),
    ).tag(config=True)

    accelerators = List(
        trait=Dict(),
        help=dedent(
            """
            Params about which accelerators should be attached to the service.
            """
        ),
    ).tag(config=True)

    placement = Dict(
        {},
        help=dedent(
            """
            List of placement constraints for all images.
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

    use_user_options = Bool(
        False,
        help=dedent(
            """
            The spawner will use the dict passed through the form
                                or as json body when using the Hub Api.
            """
        ),
    ).tag(config=True)

    jupyterhub_service_name = Unicode(
        "jupyterhub",
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
            List of JupyterHub user attributes that are used to format Spawner
            State attributes.
            """
        ),
    ).tag(config=True)

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
    def user_config_name_base(self):
        """
        Base config name for any configs that the service_owner uploads
        """
        if hasattr(self, "user_upload_name") and self.user_upload_name:
            user_upload_name = self.user_upload_name
        else:
            user_upload_name = "upload"
        return "{}-{}-{}".format(
            self.service_prefix, self.service_owner, user_upload_name
        )

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

    async def get_service(self):
        self.log.debug(
            "Getting Docker service '{}' with id: '{}'".format(
                self.service_name, self.service_id
            )
        )
        try:
            service = run_docker("inspect_service", self.service_name)
            self.log.debug("Inspect service response: {}".format(service))
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

    async def poll(self):
        """Check for a task state like `docker service ps id`"""
        service = await self.get_service()
        if service is None:
            self.log.warn("Docker service not found")
            return 0

        task_filter = {"service": service["Spec"]["Name"]}
        self.tasks = run_docker("tasks", task_filter)

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
                await self.stop()

        if running_task is not None:
            return None
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
        self.log.info("Checking for progress")
        if self.tasks:
            top_task = self.tasks[0]
            image = top_task["Spec"]["ContainerSpec"]["Image"]
            self.log.info("Spawning progress of {} with image".format(self.service_id))
            task_status = top_task["Status"]["State"]
            self.log.info("Progress task status: {}".format(task_status))
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

    async def attempt_volume_remove(self, name, max_attempts=15):
        attempt = 0
        removed = False
        # Volumes can only be removed after the service is gone
        while not removed:
            if attempt > max_attempts:
                self.log.info("Failed to remove volume {}".format(name))
                break
            self.log.info("Removing volume {}".format(name))
            removed, remove_response = remove_volume(name)
            if not removed:
                self.log.info(
                    "User: {} remove volume response: {}".format(
                        self.user.name, remove_response
                    )
                )
            await sleep(1)
            attempt += 1
        return removed

    async def start(self):
        """Start the single-user server in a docker service.
        You can specify the params for the service through
        jupyterhub_config.py or using the user_options
        """
        self.log.debug("User: {}, start spawn".format(self.user.__dict__))

        # https://github.com/jupyterhub/jupyterhub
        # /blob/master/jupyterhub/user.py#L202
        # By default jupyterhub calls the spawner passing user_options
        if self.use_user_options:
            user_options = self.user_options
        else:
            user_options = {}

        service = await self.get_service()
        if service:
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
        else:
            # Create a new service
            self.log.info(
                "Creating a new Docker service for user: {}".format(self.user.name)
            )
            container_spec = copy.deepcopy(self.container_spec)

            if isinstance(container_spec, dict) and container_spec:
                container_spec.update(user_options.get("container_spec", {}))

            # Which image to spawn
            if (
                "user_selected_image" in user_options
                and "user_selected_name" in user_options
            ):
                self.log.debug("User options received: {}".format(user_options))
                image_name = user_options["user_selected_name"]
                image_value = user_options["user_selected_image"]
                selected_image = None
                for di in self.images:
                    if image_name == di["name"] and image_value == di["image"]:
                        selected_image = copy.deepcopy(di)
                if selected_image is None:
                    err_msg = "User selected image: {} couldn't be found".format(
                        image_value
                    )
                    self.log.error(err_msg)
                    raise Exception(err_msg)
                self.log.info(
                    "Using the user selected image: {}".format(selected_image)
                )
            else:
                # Default image
                selected_image = self.images[0]
                self.log.info("Using the default image: {}".format(selected_image))

            # Extract the UID and GID to use inside the container
            uid, gid = get_user_uid_gid(container_spec)
            if "uid_gid" in selected_image:
                uid, gid = get_user_uid_gid(selected_image["uid_gid"])
                # uid_gid is not a supported option in the container_spec
            if "uid_gid" in container_spec:
                container_spec.pop("uid_gid")

            if uid:
                container_spec.update({"user": "{}".format(uid)})
            if uid and gid:
                container_spec.update({"user": "{}:{}".format(uid, gid)})

            # Check if the user supplied a user_install_files to create a ConfigReference from
            # that can be used to install into the user's container upon spawning.
            if (
                "user_install_files" in user_options
                and user_options["user_install_files"]
            ):
                for idx, user_install_file in enumerate(
                    user_options.get("user_install_files", [])
                ):
                    file_name = user_install_file["name"]
                    file_extension = user_install_file["extension"]

                    config_name = "{}-{}".format(self.user_config_name_base, idx)
                    # If an existing config_name already exists, remove
                    # the old one before creating a new one
                    if get_config(config_name)[0]:
                        pruned, pruned_response = prune_config(config_name)
                        if not pruned:
                            self.log.error(pruned_response)
                            raise Exception(pruned_response)

                    user_config_result = run_docker(
                        "create_config", config_name, user_install_file["data"]
                    )
                    if (
                        isinstance(user_config_result, dict)
                        and "ID" in user_config_result
                    ):
                        user_config_id = user_config_result.get("ID")
                        config_mount_path = os.path.join(
                            self.user_upload_destination_directory,
                            file_name + file_extension,
                        )
                        user_install_config = prepare_user_config_reference(
                            user_config_id,
                            config_name,
                            filename=config_mount_path,
                            uid=uid,
                            gid=gid,
                        )
                        self.configs.append(user_install_config)

            # Assign the image name as a label
            container_spec["labels"] = {"image_name": selected_image["name"]}

            # Setup mounts
            mounts = []
            # Global mounts
            if "mounts" in container_spec:
                mounts.extend(container_spec["mounts"])
            container_spec["mounts"] = []

            # Image mounts
            if "mounts" in selected_image:
                mounts.extend(selected_image["mounts"])

            # Prepare the dictionary that can be used
            # to format the container_spec
            format_mount_kwargs = {}
            if self.user_format_attributes:
                for attr in self.user_format_attributes:
                    if hasattr(self.user, attr):
                        value = getattr(self.user, attr)
                        if not isinstance(value, dict):
                            value = {attr: value}
                        format_mount_kwargs[attr] = value

            # Mounts can be declared as regular dictionaries
            # or as special Mountable objects (see mount.py)
            for mount in mounts:
                if isinstance(mount, dict):
                    m = VolumeMounter(mount)
                    m = await m.create(**format_mount_kwargs)
                else:
                    # Custom type mount defined
                    # Is instantiated in the config
                    m = await mount.create(**format_mount_kwargs)
                container_spec["mounts"].append(m)

            # Some envs are required by the single-user-image
            if "env" in container_spec:
                container_spec["env"].update(self.get_env())
            else:
                container_spec["env"] = self.get_env()

            # Env of image
            if "env" in selected_image and isinstance(selected_image["env"], dict):
                container_spec["env"].update(selected_image["env"])

            # Dynamic update of env values
            for env_key, env_value in container_spec["env"].items():
                stripped_value = env_value.lstrip("{").rstrip("}")
                if hasattr(self, stripped_value) and isinstance(
                    getattr(self, stripped_value), str
                ):
                    container_spec["env"][env_key] = getattr(self, stripped_value)
                if hasattr(self.user, stripped_value) and isinstance(
                    getattr(self.user, stripped_value), str
                ):
                    container_spec["env"][env_key] = getattr(self.user, stripped_value)
                if (
                    hasattr(self.user, "data")
                    and hasattr(self.user.data, stripped_value)
                    and isinstance(getattr(self.user.data, stripped_value), str)
                ):
                    container_spec["env"][env_key] = getattr(
                        self.user.data, stripped_value
                    )

            # Args of image
            if "args" in selected_image and isinstance(selected_image["args"], list):
                container_spec.update({"args": selected_image["args"]})

            if (
                "command" in selected_image
                and isinstance(selected_image["command"], list)
                or "command" in selected_image
                and isinstance(selected_image["command"], str)
            ):
                container_spec.update({"command": selected_image["command"]})

            # Log mounts config
            self.log.debug(
                "User: {} container_spec mounts: {}".format(
                    self.user, container_spec["mounts"]
                )
            )

            # Global resource_spec
            resource_spec = {}
            if hasattr(self, "resource_spec"):
                resource_spec = self.resource_spec
            resource_spec.update(user_options.get("resource_spec", {}))

            networks = None
            if hasattr(self, "networks"):
                networks = self.networks
            if user_options.get("networks") is not None:
                networks = user_options.get("networks")

            # Global Log driver
            log_driver = None
            if hasattr(self, "log_driver"):
                log_driver = self.log_driver
            if user_options.get("log_driver") is not None:
                log_driver = user_options.get("log_driver")

            accelerators = []
            if hasattr(self, "accelerators"):
                accelerators = self.accelerators
            if user_options.get("accelerators") is not None:
                accelerators = user_options.get("accelerators")

            # Global placement
            placement = None
            if hasattr(self, "placement"):
                placement = self.placement
            if user_options.get("placement") is not None:
                placement = user_options.get("placement")

            # Image resources
            if "resource_spec" in selected_image:
                resource_spec = selected_image["resource_spec"]

            # Accelerators attached to the image
            if "accelerators" in selected_image:
                accelerators = selected_image["accelerators"]

            # Placement of image
            if "placement" in selected_image:
                placement = selected_image["placement"]

            # Logdriver of image
            if "log_driver" in selected_image:
                log_driver = selected_image["log_driver"]

            # Configs attached to image
            if "configs" in selected_image and isinstance(
                selected_image["configs"], list
            ):
                for c in selected_image["configs"]:
                    if isinstance(c, dict):
                        self.configs.append(c)

            endpoint_spec = {}
            if "endpoint_spec" in selected_image:
                endpoint_spec = selected_image["endpoint_spec"]

            if self.configs:
                # Check that the supplied configs already exists
                current_configs = run_docker("configs")
                config_error_msg = (
                    "The server has a misconfigured config, "
                    "please contact an administrator to resolve this"
                )

                for c in self.configs:
                    if "config_name" not in c:
                        self.log.error(
                            "Config: {} does not have a "
                            "required config_name key".format(c)
                        )
                        raise Exception(config_error_msg)
                    if "config_id" not in c:
                        # Find the id from the supplied name
                        config_ids = [
                            cc["ID"]
                            for cc in current_configs
                            if cc["Spec"]["Name"] == c["config_name"]
                        ]
                        if not config_ids:
                            self.log.error(
                                "A config with name {} could not be found".format(
                                    c["config_name"]
                                )
                            )
                            raise Exception(config_error_msg)
                        c["config_id"] = config_ids[0]

                container_spec.update(
                    {"configs": [ConfigReference(**c) for c in self.configs]}
                )

            # Prepare the accelerators and attach it to the environment
            if accelerators:
                for accelerator in accelerators:
                    accelerator_id = accelerator.aquire(self.user.name)
                    # NVIDIA_VISIBLE_DEVICES=0:0
                    container_spec["env"]["NVIDIA_VISIBLE_DEVICES"] = "{}".format(
                        accelerator_id
                    )

            # Global container user
            if "user" in container_spec:
                container_spec["user"] = str(container_spec["user"])

            # Image user
            if "user" in selected_image:
                container_spec.update({"user": str(selected_image["user"])})

            # Global container workdir
            if "workdir" in container_spec:
                container_spec["workdir"] = str(container_spec["workdir"])

            # Image workdir
            if "workdir" in selected_image:
                container_spec.update({"workdir": str(selected_image["workdir"])})

            dynamic_value_owners = [Spawner, self, self.user]
            # Format container_spec with data from the
            # potential dynamic owners
            for dynamic_owner in dynamic_value_owners:
                try:
                    if not hasattr(dynamic_owner, "__dict__"):
                        continue
                    recursive_format(container_spec, dynamic_owner.__dict__)
                except TypeError:
                    pass

            # Log driver
            log_driver_name, log_driver_options = None, None
            if log_driver and isinstance(log_driver, dict):
                if "name" in log_driver:
                    log_driver_name = log_driver["name"]
                if "options" in log_driver:
                    log_driver_options = log_driver["options"]

            # Create the service
            # Image to spawn
            image = selected_image["image"]
            container_spec = ContainerSpec(image, **container_spec)
            resources = Resources(**resource_spec)
            placement = Placement(**placement)

            task_log_driver = None
            if log_driver_name:
                task_log_driver = DriverConfig(
                    log_driver_name, options=log_driver_options
                )

            task_spec = {
                "container_spec": container_spec,
                "resources": resources,
                "placement": placement,
            }

            if task_log_driver:
                task_spec.update({"log_driver": task_log_driver})

            task_tmpl = TaskTemplate(**task_spec)
            self.log.debug("task temp: {}".format(task_tmpl))
            # Set endpoint spec
            endpoint_spec = EndpointSpec(**endpoint_spec)

            resp = run_docker(
                "create_service",
                task_tmpl,
                name=self.service_name,
                networks=networks,
                endpoint_spec=endpoint_spec,
            )
            self.service_id = resp["ID"]
            self.log.info(
                "Created Docker service {} (id: {}) from image {}"
                " for user {}".format(
                    self.service_name, self.service_id[:7], image, self.user
                )
            )
            await self.wait_for_running_tasks()

        ip = self.service_name
        port = self.service_port
        self.log.debug(
            "Active service: '{}' with user '{}'".format(
                self.service_name, self.user.name
            )
        )

        # we use service_name instead of ip
        # https://docs.docker.com/engine/swarm/networking/#use-swarm-mode-service-discovery
        # service_port is actually equal to 8888
        return ip, port

    async def stop(self, now=False):
        """Stop and remove the service
        Consider using stop/start when Docker adds support
        """
        self.log.info(
            "Stopping and removing Docker service {} (id: {}) owned by: {}".format(
                self.service_name, self.service_id[:7], self.user.name
            )
        )

        service = await self.get_service()
        if not service:
            self.log.warn("Docker service not found")
            return

        self.log.debug("Docker service {}".format(service["Spec"]))
        # lookup mounts before removing the service
        volumes = []
        if "Mounts" in service["Spec"]["TaskTemplate"]["ContainerSpec"]:
            volumes = service["Spec"]["TaskTemplate"]["ContainerSpec"]["Mounts"]

        # lookup user configs before removing the service
        user_upload_configs = []
        service_configs = service["Spec"]["TaskTemplate"]["ContainerSpec"].get(
            "Configs", []
        )
        for config in service_configs:
            config_name = config.get("ConfigName", None)
            if config_name and self.user_config_name_base in config_name:
                user_upload_configs.append(config)

        # Even though it returns the service is gone
        # the underlying containers are still being removed
        removed_service = run_docker("remove_service", service["ID"])
        if removed_service:
            self.log.info(
                "Docker service {} (id: {}) removed".format(
                    self.service_name, self.service_id[:7]
                )
            )
            for volume in volumes:
                labels = volume.get("VolumeOptions", {}).get("Labels", {})
                # Whether the volume should be kept
                if "autoremove" in labels and labels["autoremove"] != "False":
                    self.log.debug("Volume {} is not kept".format(volume))
                    if "Source" in volume:
                        # Validate the volume exists
                        try:
                            run_docker("inspect_volume", volume["Source"])
                        except docker.errors.NotFound:
                            self.log.info("No volume named: " + volume["Source"])
                        else:
                            await self.attempt_volume_remove(volume["Source"])
                    else:
                        self.log.error(
                            "Volume {} didn't have a 'Source' key so it "
                            "can't be removed".format(volume)
                        )
            for config in user_upload_configs:
                self.log.info("Removing config: {}".format(config))
                if not prune_config(config["ConfigName"], logger=self.log):
                    self.log.error(
                        "Can't remove config: {} because it does not exist".format(
                            config["ConfigName"]
                        )
                    )

    async def wait_for_running_tasks(self, max_attempts=20, max_preparing=30):
        running = False
        num_preparing, attempt = 0, 0
        while not running:
            service = await self.get_service()
            task_filter = {"service": service["Spec"]["Name"]}
            self.tasks = run_docker("tasks", task_filter)
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
            else:
                num_preparing += 1
            if num_preparing > max_preparing:
                return False
            await sleep(1)
