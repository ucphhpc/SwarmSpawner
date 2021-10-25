import copy
from tornado import gen
from traitlets.config import LoggingConfigurable, Config
from docker.types import DriverConfig, Mount
from flatten_dict import flatten


class Mounter(LoggingConfigurable):
    def __init__(self, config):
        LoggingConfigurable.__init__(self)
        if not isinstance(config, dict):
            raise Exception("A dictionary typed config is expected")
        if not config:
            raise Exception("A non-zero sized dictionary is expected")
        # Ensure that we don't change the passed in config,
        # But only use it. Deep is allowed if it is of type Config
        self.config = copy.deepcopy(Config(config))

    @gen.coroutine
    def init(self, owner=None, keep=True):
        # Check if username specific source is expected
        if (
            "source" in self.config
            and owner is not None
            and "username" in self.config["source"]
        ):
            self.config["source"] = self.config["source"].format(username=owner)
        # Labels are only allowed in volume types
        if self.config["type"] != "volume":
            return None

        if "labels" not in self.config:
            self.config["labels"] = {"keep": str(keep)}
        elif not isinstance(self.config["labels"], dict):
            raise TypeError("labels volume config key must be a dict")
        elif "keep" not in self.config["labels"]:
            self.config["labels"] = {"keep": str(keep)}

    @gen.coroutine
    def create(self, data=None, owner=None, keep=True):
        pass


class VolumeMounter(Mounter):
    def __init__(self, config):
        Mounter.__init__(self, config)

    @gen.coroutine
    def create_mount(self):
        mount = {}
        mount.update(self.config)
        return Mount(**mount)

    @gen.coroutine
    def create(self, data=None, owner=None, keep=True):
        self.log.debug("Creating mount {}".format(data))
        yield self.validate_config()
        yield self.init(owner, keep)
        mount = yield self.create_mount()
        return mount

    @gen.coroutine
    def validate_config(self):
        self.log.debug("validate_config")
        required_config_keys = ["type", "source", "target"]
        missing_keys = [key for key in required_config_keys if key not in self.config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered, " "due to missing keys"
            )

        required_config_values = ["type", "target"]
        empty_values = [key for key in required_config_values if not self.config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered, " "due to missing values"
            )

        # validate types
        for key, val in self.config.items():
            if key == "labels" or key == "driver_options":
                if not isinstance(val, dict):
                    raise TypeError(
                        "{} is expected to be of type: {}".format(key, dict)
                    )
            elif key == "driver_config":
                if not isinstance(val, str) and not isinstance(val, DriverConfig):
                    raise TypeError(
                        "{} is expected to be of type: {} or {}".format(
                            key, str, DriverConfig
                        )
                    )
            elif key == "read_only":
                if not isinstance(val, bool):
                    raise TypeError(
                        "{} is expected to be of type: {}".format(key, bool)
                    )
            else:
                if not isinstance(val, str):
                    raise TypeError("{} is expected to be of {} type".format(key, str))


class SSHFSMounter(Mounter):
    def __init__(self, config):
        Mounter.__init__(self, config)

    @gen.coroutine
    def create_mount(self, data):
        self.log.debug("create_mount: {}".format(data))

        # validate required driver data is present
        err, err_msg = False, []
        if (
            "sshcmd" not in self.config["driver_options"]
            or self.config["driver_options"]["sshcmd"] == ""
        ):
            err_msg.append(
                "create_mount requires that the 'sshcmd'"
                "driver_options key is set to a nonempty value"
            )
            err = True

        if (
            "id_rsa" not in self.config["driver_options"]
            and "password" not in self.config["driver_options"]
            or "id_rsa" in self.config["driver_options"]
            and "password" in self.config["driver_options"]
        ):
            err_msg.append(
                "create_mount requires either a 'id_rsa'"
                " or 'password' driver_options key"
            )
            err = True

        if (
            "id_rsa" in self.config["driver_options"]
            and self.config["driver_options"]["id_rsa"] == ""
            or "password" in self.config["driver_options"]
            and self.config["driver_options"]["password"] == ""
        ):
            err_msg.append(
                "create_mount requires a nonempty value from either "
                "'id_rsa' or 'password'"
            )
            err = True

        if err:
            self.log.error("create_mount failed: {}".format(",".join(err_msg)))
            raise Exception("An error occurred during mount creation")

        driver = {"driver_config": self.config["driver_config"], "driver_options": {}}
        driver["driver_options"].update(self.config["driver_options"])
        del self.config["driver_options"]

        # Setup driver
        # look for values that should be dynamically assigned from data
        for option_key, option_value in driver["driver_options"].items():
            if option_value == "{" + option_key + "}":
                dyn_value = yield self.get_from(option_key, data)
                if dyn_value:
                    driver["driver_options"][option_key] = dyn_value

        # Legacy options that will be deprecated
        if driver["driver_options"]["sshcmd"] == "{sshcmd}":
            # Validate that the proper values are present
            username = yield self.get_from("USERNAME", data)
            path = yield self.get_from("PATH", data)
            if username and path:
                driver["driver_options"]["sshcmd"] = username + path

        if (
            "id_rsa" in driver["driver_options"]
            and driver["driver_options"]["id_rsa"] == "{id_rsa}"
        ):
            key = yield self.get_from("PRIVATEKEY", data)
            if key:
                driver["driver_options"]["id_rsa"] = key

        if (
            "port" in driver["driver_options"]
            and driver["driver_options"]["port"] == "{port}"
        ):
            port = yield self.get_from("PORT", data)
            if port:
                driver["driver_options"]["port"] = port
            else:
                driver["driver_options"]["port"] = "22"

        mount = {}
        mount.update(self.config)
        mount["driver_config"] = DriverConfig(
            name=driver["driver_config"], options=driver["driver_options"]
        )
        return Mount(**mount)

    @gen.coroutine
    def validate_config(self):
        self.log.debug("validate_config")
        required_config_keys = [
            "type",
            "driver_config",
            "driver_options",
            "source",
            "target",
        ]
        missing_keys = [key for key in required_config_keys if key not in self.config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(",".join(missing_keys)))
            raise KeyError(
                "A mount configuration error was encountered, " "due to missing keys"
            )

        required_config_values = ["type", "driver_config", "driver_options", "target"]
        empty_values = [key for key in required_config_values if not self.config[key]]
        if empty_values:
            self.log.error(
                "Missing configuring values {}".format(",".join(empty_values))
            )
            raise ValueError(
                "A mount configuration error was encountered, " "due to missing values"
            )

        # validate types
        for key, val in self.config.items():
            if key == "driver_options" or key == "labels":
                if not isinstance(val, dict):
                    raise TypeError(
                        "{} is expected to be of a {} type".format(key, dict)
                    )
            else:
                if not isinstance(val, str):
                    raise TypeError("{} is expected to be of {} type".format(key, str))

    @gen.coroutine
    def get_from(self, key, data):
        if data is None or not isinstance(data, dict):
            self.log.error("validate_data {} is not valid".format(data))
            raise Exception(
                "Missing information to mount the host in question "
                "with. Try to reinitialize them"
            )

        flatten_data = flatten(data, reducer="tuple")
        for f_key, f_val in flatten_data.items():
            if key in f_key:
                return f_val
        return None

    @gen.coroutine
    def create(self, data=None, owner=None, keep=True):
        self.log.debug("Creating mount {}".format(data))
        yield self.init(owner, keep)
        yield self.validate_config()
        mount = yield self.create_mount(data)
        return mount
