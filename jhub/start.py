import os
from jhub.defaults import default_base_path
from jhub.io import makedirs


def create_base_path(path=default_base_path):
    return makedirs(path)


def prepare_spawner_config_dir(base_path=default_base_path):
    if not os.path.exists(base_path) and not create_base_path(base_path):
        return False
    return True
