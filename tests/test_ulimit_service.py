import docker
import requests
import logging
import pytest
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath
from urllib.parse import urljoin
from util import (
    get_service,
    wait_for_site,
    wait_for_service_task,
    get_service_user,
    delete,
)

HUB_IMAGE_TAG = "hub:test"
MOUNT_IMAGE_TAG = "ucphhpc/ssh-mount-dummy"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"
MOUNT_SERVICE_NAME = "mount_target"
PORT = 8000

JHUB_URL = "http://127.0.0.1:{}".format(PORT)


# Logger
logging.basicConfig(level=logging.INFO)
test_logger = logging.getLogger()

# Test data
rand_key = "".join(SystemRandom().choice("0123456789abcdef") for _ in range(32))


# root dir
hub_path = dirname(dirname(__file__))
hub_image = {"path": hub_path, "tag": HUB_IMAGE_TAG, "rm": True, "pull": False}

# If the test host has multiple interfaces that the
# swarm can listen, use -> 'advertise_addr': 'host-ip'
swarm_config = {}
network_config = {
    "name": NETWORK_NAME,
    "driver": "overlay",
    "options": {"subnet": "192.168.0.0/24"},
    "attachable": True,
}
hub_config = join(dirname(realpath(__file__)), "configs", "ulimit_jupyterhub_config.py")
hub_service = {
    "image": HUB_IMAGE_TAG,
    "name": HUB_SERVICE_NAME,
    "mounts": [
        ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
        ":".join([hub_config, "/etc/jupyterhub/jupyterhub_config.py", "ro"]),
    ],
    "networks": [NETWORK_NAME],
    "endpoint_spec": EndpointSpec(ports={PORT: PORT}),
    "env": ["JUPYTERHUB_CRYPT_KEY=" + rand_key],
    "command": ["jupyterhub", "-f", "/etc/jupyterhub/jupyterhub_config.py"],
}


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_ulimit_service(image, swarm, network, make_service):
    """Test that logging in as a new user creates a new docker service."""
    test_logger.info("Start of service testing")
    make_service(hub_service)
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_spawn = client.services.list()
    test_logger.info("Pre test services: {}".format(services_before_spawn))

    username = "a-new-user"
    password = "just magnets"
    test_logger.info("Authenticating with user: {}".format(username))
    assert wait_for_site(JHUB_URL) is True

    with requests.Session() as s:
        # Refresh cookies
        s.get(JHUB_URL)

        # Login
        test_logger.info("Authenticating with user: {}".format(username))
        login_response = s.post(
            urljoin(JHUB_URL, "/hub/login?next="),
            data={"username": username, "password": password},
            params={"_xsrf": s.cookies["_xsrf"]},
        )
        test_logger.info("Login response message: {}".format(login_response.text))
        assert login_response.status_code == 200

        # Spawn a notebook
        spawn_form_resp = s.get(urljoin(JHUB_URL, "/hub/spawn"))
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))

        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text

        payload = {"dockerimage": "ucphhpc/base-notebook:latest"}
        spawn_resp = s.post(
            urljoin(JHUB_URL, "/hub/spawn"),
            data=payload,
            params={"_xsrf": s.cookies["_xsrf"]},
        )
        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        services = client.services.list()
        test_logger.info("Post spawn services: {}".format(services))

        target_service_name = "{}-".format("jupyter")
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Verify that a task is succesfully running
        running_task = wait_for_service_task(
            client, spawned_service, filters={"desired-state": "running"}, timeout=300
        )
        assert running_task

        # wait for user home
        home_resp = s.get(urljoin(JHUB_URL, "/user/{}/tree?".format(username)))
        assert home_resp.status_code == 200

        # Check that the ulimit for the service is set to unlimited
        container = client.containers.get(
            running_task["Status"]["ContainerStatus"]["ContainerID"]
        )
        # TODO, assert the ulimit

        # Remove via the web interface
        delete_headers = {"Referer": urljoin(JHUB_URL, "/hub/home"), "Origin": JHUB_URL}

        jhub_user = get_service_user(spawned_service)
        delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(jhub_user))

        # Wait for the server to finish deleting
        deleted = delete(
            s,
            delete_url,
            headers=delete_headers,
            params={"_xsrf": s.cookies["_xsrf"]},
        )
        assert deleted

        # double check it is gone
        deleted_service = get_service(client, target_service_name)
        assert deleted_service is None
        test_logger.info("End of test service")
