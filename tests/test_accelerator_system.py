import logging
import pytest
import docker
import requests
from os.path import join, dirname, realpath
from tests.defaults import (
    JHUB_URL,
    hub_image,
    swarm_config,
    network_config,
    hub_service,
)
from tests.helpers import (
    login,
    spawn_notebook,
    get_running_notebook,
    stop_notebook,
    wait_for_notebook,
)
from tests.util import wait_for_site

new_hub_config = join(
    dirname(realpath(__file__)), "configs", "accelerator_jupyterhub_config.py"
)
new_mounts = [
    ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
    ":".join([new_hub_config, "/etc/jupyterhub/jupyterhub_config.py", "ro"]),
]
hub_service["mounts"] = new_mounts

# Logger
logging.basicConfig(level=logging.DEBUG)
test_logger = logging.getLogger()


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_access_restriction(image, swarm, network, make_service):
    make_service(hub_service)
    assert wait_for_site(JHUB_URL) is True

    client = docker.from_env()
    services_before_spawn = client.services.list()
    test_logger.info("Pre test services: {}".format(services_before_spawn))

    username = "basic_user"
    password = "just magnets"

    test_logger.info("Authenticating with user: {}".format(username))

    with requests.Session() as s:
        # Login
        test_logger.info("Authenticating with user: {}".format(username))
        login_response = login(s, username, password)
        test_logger.info("Login response message: {}".format(login_response))

        # Spawn a notebook
        user_image_name = "GPU Notebook"
        user_image_data = "ucphhpc/gpu-notebook:latest"
        spawned = spawn_notebook(s, username, user_image_name, user_image_data)
        assert spawned

        # Wait for it to start
        running_notebook = get_running_notebook(s, username)
        assert running_notebook
        assert wait_for_notebook(s, running_notebook)

        # Validate that the accelerator is associated

        # # Delete the spawned service
        # stopped = stop_notebook(s, username)
        # assert stopped

        # # Try to start a restricted notebook
        # user_image_name = "Restricted Notebook"
        # user_image_data = "ucphhpc/base-notebook:latest"
        # spawned = spawn_notebook(s, username, user_image_name, user_image_data)

        # # Validate that the notebook is not running
        # notebook = get_running_notebook(s, username)
        # assert not notebook
