import copy
from tornado import gen
from traitlets.config import LoggingConfigurable, Config
from docker.types import DriverConfig, Mount
from jhub.util import recursive_format


class Mounter(LoggingConfigurable):
    def __init__(self, config):
        LoggingConfigurable.__init__(self)
        if not isinstance(config, dict):
            raise Exception("A dictionary typed config is expected")
        if not config:
            raise Exception("A non-zero sized dictionary is expected")
        # Ensure that we don't change the passed in config,
        # But only use it. Deep copy is allowed if it is of type Config
        self.log.debug("instantiating Mounter with config: {}".format(config))
        self.config = copy.deepcopy(Config(config))

    @gen.coroutine
    def gen_config_copy(self):
        return copy.deepcopy(self.config)

    @gen.coroutine
    def format_config(self, config, **kwargs):
        # Dynamically overload the mount config
        self.log.debug("formatting mount config: {} with: {}".format(config, kwargs))
        for key, value in kwargs.items():
            recursive_format(config, value)
        self.log.debug("new formatted config: {}".format(config))


class VolumeMounter(Mounter):
    def __init__(self, config):
        Mounter.__init__(self, config)

    @gen.coroutine
    def create_mount(self, config):
        mount = {}
        mount.update(config)
        return Mount(**mount)

    @gen.coroutine
    def create(self, **format_config_kwargs):
        self.log.debug(
            "Creating VolumeMount with options {}".format(format_config_kwargs)
        )
        new_config = yield self.gen_config_copy()
        yield self.format_config(new_config, **format_config_kwargs)
        yield self.validate_config(new_config)
        mount = yield self.create_mount(new_config)
        return mount

    @gen.coroutine
    def validate_config(self, config):
        self.log.debug("validate_config")
        required_config_keys = ["source", "target"]
        missing_keys = [key for key in required_config_keys if key not in config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered due to missing keys."
            )

        required_config_values = ["target"]
        empty_values = [key for key in required_config_values if not config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered due to missing values."
            )


class SSHFSMounter(Mounter):
    def __init__(self, config):
        Mounter.__init__(self, config)

    @gen.coroutine
    def create_mount(self, config):
        self.log.debug("create_mount from config: {}".format(config))
        # Adapt mount options into appropriate types
        driver_config = DriverConfig(
            config["driver_config"]["name"],
            config["driver_config"]["options"],
        )

        mount_config = {}
        mount_config.update(config)
        # Override the DriverConfig to be the correct type
        # as expected by the Docker module.
        mount_config["driver_config"] = driver_config
        return Mount(**mount_config)

    @gen.coroutine
    def validate_config(self, config):
        self.log.debug("validate_config")
        required_config_keys = ["source", "target", "type", "driver_config"]
        missing_keys = [key for key in required_config_keys if key not in config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered, " "due to missing keys"
            )

        required_config_values = ["type", "driver_config", "target"]
        empty_values = [key for key in required_config_values if not config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered, due to missing values"
            )

    @gen.coroutine
    def create(self, **format_config_kwargs):
        new_config = yield self.gen_config_copy()
        yield self.format_config(new_config, **format_config_kwargs)
        yield self.validate_config(new_config)
        mount = yield self.create_mount(new_config)
        return mount
