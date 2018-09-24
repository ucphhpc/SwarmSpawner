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
        self.config = Config(config)

    @gen.coroutine
    def create(self, data=None):
        return None


class LocalVolumeMounter(Mounter):

    def __init__(self, config):
        super(Mounter).__init__(config)

    @gen.coroutine
    def create(self, data=None):
        return None


class SSHFSMounter(Mounter):

    def __init__(self, config):
        Mounter.__init__(self, config)

    @gen.coroutine
    def create_mount(self, data):
        self.log.debug("create_mount: {}".format(data))

        # validate required driver data is present
        err, err_msg = False, []
        if 'sshcmd' not in self.config['driver_options'] \
                or self.config['driver_options']['sshcmd'] == '':
            err_msg.append("create_mount requires that the 'sshcmd'"
                           "driver_options key is set to a nonempty value")
            err = True

        if 'id_rsa' not in self.config['driver_options'] \
                and 'password' not in self.config['driver_options'] \
                or 'id_rsa' in self.config['driver_options'] \
                and 'password' in self.config['driver_options']:
            err_msg.append("create_mount requires either a 'id_rsa'"
                           " or 'password' driver_options key")
            err = True

        if 'id_rsa' in self.config['driver_options'] \
                and self.config['driver_options']['id_rsa'] == '' \
                or 'password' in self.config['driver_options'] \
                and self.config['driver_options']['password'] == '':
            err_msg.append("create_mount requires a nonempty value from either "
                           "'id_rsa' or 'password'")
            err = True

        if err:
            self.log.error("create_mount failed: {}".format(','.join(err_msg)))
            raise Exception("An error occurred during mount creation")

        driver = {'driver_config': self.config['driver_config'],
                  'driver_options': {}}
        driver['driver_options'].update(self.config['driver_options'])
        del self.config['driver_options']

        # Setup driver
        if driver['driver_options']['sshcmd'] == '{sshcmd}':
            # Validate that the proper values are present
            username = yield self.get_from('USERNAME', data)
            path = yield self.get_from('PATH', data)
            driver['driver_options']['sshcmd'] = username + path

        if driver['driver_options']['id_rsa'] == '{id_rsa}':
            key = yield self.get_from('PRIVATEKEY', data)
            driver['driver_options']['id_rsa'] = key

        mount = {}
        mount.update(self.config)
        mount['driver_config'] = DriverConfig(
            name=driver['driver_config'],
            options=driver['driver_options'])
        return Mount(**mount)

    @gen.coroutine
    def validate_config(self):
        self.log.debug("validate_config")
        required_config_keys = ['type', 'driver_config',
                                'driver_options', 'source', 'target']
        missing_keys = [key for key in required_config_keys
                        if key not in self.config]

        if missing_keys:
            self.log.error("Missing configure keys {}".format(
                ','.join(missing_keys)))
            raise Exception("A mount configuration error was encountered, "
                            "due to missing keys")

        required_config_values = ['type', 'driver_config',
                                  'driver_options', 'target']
        empty_values = [key for key in required_config_values
                        if not self.config[key]]
        if empty_values:
            self.log.error("Missing configuring values {}".format(
                ','.join(empty_values)))
            raise Exception("A mount configuration error was encountered, "
                            "due to missing values")

        # validate types
        for key, val in self.config.items():
            if key == 'driver_options':
                if not isinstance(val, dict):
                    raise Exception("{} is expected to be of a {} type".format(
                        key, dict))
            else:
                if not isinstance(val, str):
                    raise Exception("{} is expected to be of {} type".format(
                        key, str))

    @gen.coroutine
    def get_from(self, key, data):
        if data is None or not isinstance(data, dict):
            self.log.error("validate_data {} is not valid".format(data))
            raise Exception("Missing information to mount the host in question "
                            "with. Try to reinitialize them")

        flatten_data = flatten(data, reducer='tuple')
        for f_key, f_val in flatten_data.items():
            if key in f_key:
                return f_val
        return None

    @gen.coroutine
    def create(self, data=None, owner=None):
        self.log.info("Creating a new mount {}".format(data))
        # Check if username specfic source is expected
        if 'source' in self.config and owner is not None:
            self.config['source'] = self.config['source'].format(
                username=owner
            )

        yield self.validate_config()
        mount = yield self.create_mount(data)
        return mount

    @gen.coroutine
    def remove(self):
        pass
