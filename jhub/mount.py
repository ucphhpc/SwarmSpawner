from tornado import gen

class Mounter:


    def __init__(self, config):
        if not isinstance(config, dict):
            raise Exception("A dictionary typed config is expected")
        if not config:
            raise Exception("A non-zero sized dictionary is expected")
        self.config = config

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
        super(Mounter).__init__(config)

    @gen.coroutine
    def init(self, data):
        self.log.debug("init_mount: {}".format(data))
        # Volume name

        # Custom volume
            # Replace if placeholder is present
            if 'sshcmd' in mount['driver_options']:
                if mount['driver_options']['sshcmd'] == '{sshcmd}':
                    mount['driver_options']['sshcmd'] \
                        = self.user.mount['USERNAME'] \
                        + self.user.mount['PATH']

                elif mount['driver_options']['sshcmd'] == '':
                    self.log.error(
                        "User: {} has a misconfigured mount {}, missing "
                        "sshcmd value".format(self.user, mount[
                            'driver_options']))
                    raise Exception("Mount is misconfigured, missing sshcmd")

            if 'id_rsa' in mount['driver_options']:
                if mount['driver_options']['id_rsa'] == '{id_rsa}':
                    mount['driver_options']['id_rsa'] = self.user.mount[
                        'PRIVATEKEY']

                elif mount['driver_options']['id_rsa'] == '':
                    if 'password' not in mount['driver_options'] or \
                       mount['driver_options']['password'] == '':
                        self.log.error(
                            "User: {} has a misconfigured mount {},"
                            " missing both id_rsa and password "
                            "value".format(self.user, mount['driver_options']))
                        raise Exception("Mount is misconfigured, "
                                        "no authentication secret is available")

            mount['driver_config'] = DriverConfig(
                name=mount['driver_config'],
                options=mount['driver_options'])

    @gen.coroutine
    def validate_config(self):
        error = False
        msg = []
        if 'type' not in self.config:
            msg.append("Mount type is not set")


        if 'driver_config' not in self.config:
            msg.append()


        if error:
            self.log.error("A configuration error was encountered {}".format())
            raise Exception("A mount configuration error was encountered")


    @gen.coroutine
    def validate_data(self, data):
        # Validate required dictionary keys
        required_keys = ['HOST', 'USERNAME',
                         'PATH', 'PRIVATEKEY']
        missing_keys = [key for key in required_keys if
                        key not in data]
        # Skip validation if debug
        if len(missing_keys) > 0:
            self.log.error(
                "User: {} missing mount keys: {}"
                    .format(self.user,
                            ",".join(missing_keys)))
            raise Exception(
                "Mount keys are available "
                "but missing the following items: {} "
                "try reinitialize them "
                "through the access interface"
                .format(",".join(missing_keys))
            )
        else:
            self.log.info(
                "User: {} mount contains:"
                " {}".format(self.user, self.user.mount))

    @gen.coroutine
    def create(self, data=None):
        if data is None:
            raise Exception("Missing information to mount the host in question with."
                            "Try to reinitialize them")

        yield self.validate_config()
        yield self.validate_data(data)
        mount = yield self.init(data)

        return mount

    #
    #
    # @gen.coroutine
    # def init_mount(self, mount):
    #     self.log.debug("init_mount: {}".format(mount))
    #     # Volume name
    #     if 'source' in mount:
    #         mount['source'] = mount['source'].format(
    #             username=self.service_owner)
    #
    #         # If a previous user volume is present, remove it
    #         try:
    #             yield self.docker('inspect_volume', mount['source'])
    #         except docker.errors.NotFound:
    #             self.log.info("No volume named: " + mount['source'])
    #         else:
    #             yield self.remove_volume(mount['source'])
    #
    #     # Custom volume
    #     if 'driver_config' in mount:
    #         # Replace if placeholder is present
    #         if 'sshcmd' in mount['driver_options']:
    #             if mount['driver_options']['sshcmd'] == '{sshcmd}':
    #                 mount['driver_options']['sshcmd'] \
    #                     = self.user.mount['USERNAME'] \
    #                     + self.user.mount['PATH']
    #
    #             elif mount['driver_options']['sshcmd'] == '':
    #                 self.log.error(
    #                     "User: {} has a misconfigured mount {}, missing "
    #                     "sshcmd value".format(self.user, mount[
    #                         'driver_options']))
    #                 raise Exception("Mount is misconfigured, missing sshcmd")
    #
    #         if 'id_rsa' in mount['driver_options']:
    #             if mount['driver_options']['id_rsa'] == '{id_rsa}':
    #                 mount['driver_options']['id_rsa'] = self.user.mount[
    #                     'PRIVATEKEY']
    #
    #             elif mount['driver_options']['id_rsa'] == '':
    #                 if 'password' not in mount['driver_options'] or \
    #                    mount['driver_options']['password'] == '':
    #                     self.log.error(
    #                         "User: {} has a misconfigured mount {},"
    #                         " missing both id_rsa and password "
    #                         "value".format(self.user, mount['driver_options']))
    #                     raise Exception("Mount is misconfigured, "
    #                                     "no authentication secret is available")
    #
    #         mount['driver_config'] = DriverConfig(
    #             name=mount['driver_config'],
    #             options=mount['driver_options'])
    #         del mount['driver_options']
    #     self.log.debug("End of init mount: {}".format(mount))