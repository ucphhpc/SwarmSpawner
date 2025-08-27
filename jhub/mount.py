import copy
from traitlets.config import LoggingConfigurable
from docker.types import DriverConfig, Mount
from jhub.util import recursive_format


class Mounter(LoggingConfigurable):
    def __init__(self, mount_config):
        LoggingConfigurable.__init__(self)
        if not isinstance(mount_config, dict):
            raise Exception("A dictionary typed config is expected")
        if not mount_config:
            raise Exception("A non-zero sized dictionary is expected")
        # Ensure that we don't change the passed in config,
        # But only use it. Deep copy is allowed if it is of type Config
        self.log.debug("instantiating Mounter with config: {}".format(mount_config))
        self._mount_config = mount_config

    @property
    def mount_config(self):
        self.log.debug("Retriving mount config: {}".format(self._mount_config))
        return self._mount_config

    @mount_config.setter
    def mount_config(self, mount_config):
        self.log.debug(
            "Setting config: {} overwriting: {}".format(
                self._mount_config, mount_config
            )
        )
        self._mount_config = mount_config

    async def gen_config_copy(self):
        return copy.deepcopy(self.mount_config)

    async def format_config(self, mount_config, **kwargs):
        # Dynamically overload the mount config
        self.log.debug(
            "formatting mount config: {} with: {}".format(mount_config, kwargs)
        )
        for key, value in kwargs.items():
            recursive_format(mount_config, value)
        self.log.debug("new formatted config: {}".format(mount_config))


class VolumeMounter(Mounter):
    def __init__(self, mount_config):
        Mounter.__init__(self, mount_config)

    async def create_mount(self, mount_config):
        mount_settings = {}
        mount_settings.update(mount_config)
        return Mount(**mount_settings)

    async def create(self, **format_mount_config_kwargs):
        self.log.debug(
            "Creating VolumeMount with options {}".format(format_mount_config_kwargs)
        )
        new_mount_config = await self.gen_config_copy()
        await self.format_config(new_mount_config, **format_mount_config_kwargs)
        await self.validate_config(new_mount_config)
        mount = await self.create_mount(new_mount_config)
        return mount

    async def validate_config(self, mount_config):
        self.log.debug("validate_config")
        required_config_keys = ["source", "target"]
        missing_keys = [key for key in required_config_keys if key not in mount_config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered due to missing keys."
            )

        required_config_values = ["target"]
        empty_values = [key for key in required_config_values if not mount_config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered due to missing values."
            )


class SSHFSMounter(Mounter):
    def __init__(self, mount_options):
        Mounter.__init__(self, mount_options)

    async def create_mount(self, mount_config):
        self.log.debug("create_mount from config: {}".format(mount_config))
        # Adapt mount options into appropriate types
        driver_config = DriverConfig(
            mount_config["driver_config"]["name"],
            mount_config["driver_config"]["options"],
        )

        mount_settings = {}
        mount_settings.update(mount_config)
        # Override the DriverConfig to be the correct type
        # as expected by the Docker module.
        mount_settings["driver_config"] = driver_config
        return Mount(**mount_settings)

    async def validate_config(self, mount_config):
        self.log.debug("validate_config")
        required_config_keys = ["source", "target", "type", "driver_config"]
        missing_keys = [key for key in required_config_keys if key not in mount_config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered, " "due to missing keys"
            )

        required_config_values = ["type", "driver_config", "target"]
        empty_values = [key for key in required_config_values if not mount_config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered, due to missing values"
            )

    async def create(self, **format_mount_config_kwargs):
        new_config = await self.gen_config_copy()
        await self.format_config(new_config, **format_mount_config_kwargs)
        await self.validate_config(new_config)
        mount = await self.create_mount(new_config)
        return mount
