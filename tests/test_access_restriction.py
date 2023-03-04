import logging
import pytest
import docker
import requests
import json
from urllib.parse import urljoin
from os.path import join, dirname, realpath
from tests.defaults import (
    JHUB_URL,
    hub_image,
    swarm_config,
    network_config,
    hub_service
)
from tests.util import wait_for_site

hub_config = join(dirname(realpath(__file__)), "configs", "access_jupyterhub_config.py")
new_mounts = {
    "mounts": [
        ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
        ":".join([hub_config, "/etc/jupyterhub/jupyterhub_config.py", "ro"]),
    ]
}
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
    admin_user = "admin_user"
    password = "just magnets"

    test_logger.info("Authenticating with user: {}".format(username))

    with requests.Session() as s:
        # Login
        test_logger.info("Authenticating with user: {}".format(username))
        login_response = s.post(
            urljoin(JHUB_URL, "/hub/login"),
            data={"username": username, "password": password},
        )
        test_logger.info("Login response message: {}".format(login_response.text))
        assert login_response.status_code == 200

        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))

        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text

        user_image_name = "Basic Python Notebook"
        user_image_data = "ucphhpc/base-notebook:latest"
        payload = {
            "select_image": json.dumps(
                {"image": user_image_data, "name": user_image_name}
            )
        }
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload)
        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        # Delete the spawned service
        delete_headers = {"Referer": urljoin(JHUB_URL, "/hub/home"), "Origin": JHUB_URL}

        jhub_user = get_service_user(spawned_service)
        delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(jhub_user))

        deleted = delete(s, delete_url, headers=delete_headers)
        assert deleted

        # Try to spawn a restricted service
        spawned = spawn_notebook(user, user_image_name, user_image_data)
        assert spawned
        
