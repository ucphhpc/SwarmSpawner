from jhub.io import load, exists


class Access:
    db = {}

    def __init__(self, db_config):
        self.db = db_config

    @staticmethod
    def restricted(image_configuration):
        return "access" in image_configuration

    def allowed(self, username, image_configuration):
        if "access" not in image_configuration:
            return True

        if "groups" in image_configuration["access"]:
            for allowed_group in image_configuration["access"]["groups"]:
                if allowed_group in self.db:
                    for db_user in self.db[allowed_group]:
                        if db_user == username:
                            return True
        if "users" in image_configuration["access"]:
            for allowed_user in image_configuration["access"]["users"]:
                if allowed_user == username:
                    return True
        return False


class AccessLists(Access):
    def __init__(self, db_config):
        for key, value in db_config.items():
            self.db[key] = value


class AccessFiles(Access):
    def __init__(self, db_config):
        """Read in the users from the files"""
        for key, value in db_config.items():
            users = []
            for filename in value:
                if not exists(filename):
                    raise IOError("Failed to find AccessFile: {}".format(filename))
                users = load(filename, readlines=True)
                if not users:
                    raise ValueError()(
                        "Nothing was read from AccessFile: {}".format(filename)
                    )
            self.db[key] = users
