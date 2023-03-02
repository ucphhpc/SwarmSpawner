import docker
import json
import time
import requests
import logging
import pytest
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath
from urllib.parse import urljoin
from util import (
    get_service,
    get_task_image,
    get_service_labels,
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
hub_config = join(dirname(realpath(__file__)), "configs", "jupyterhub_config.py")
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
def test_creates_service(image, swarm, network, make_service):
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
        # login
        test_logger.info("Authenticating with user: {}".format(username))
        login_response = s.post(
            JHUB_URL + "/hub/login?next=",
            data={"username": username, "password": password},
        )
        test_logger.info("Login response message: {}".format(login_response.text))
        assert login_response.status_code == 200
        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))

        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text

        payload = {"dockerimage": "ucphhpc/base-notebook:latest"}
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload)
        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        services = client.services.list()
        test_logger.info("Post spawn services: {}".format(services))

        target_service_name = "{}-{}-{}".format("jupyter", username, "1")
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Verify that a task is succesfully running
        running_task = wait_for_service_task(
            client, spawned_service, filters={"desired-state": "running"}, timeout=300
        )
        assert running_task

        # wait for user home
        home_resp = s.get(JHUB_URL + "/user/{}/tree?".format(username))
        assert home_resp.status_code == 200
        # Remove via the web interface
        delete_headers = {"Referer": urljoin(JHUB_URL, "/hub/home"), "Origin": JHUB_URL}

        jhub_user = get_service_user(spawned_service)
        delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(jhub_user))

        pending = True
        num_wait, max_wait = 0, 30
        while pending or num_wait > max_wait:
            num_wait += 1
            resp = s.delete(delete_url, headers=delete_headers)
            test_logger.info(
                "Response from removing the user server: {}".format(resp.text)
            )
            if resp.status_code == 204:
                pending = False
            time.sleep(1)

        assert resp.status_code == 204

        # double check it is gone
        deleted_service = get_service(client, target_service_name)
        assert deleted_service is None
        test_logger.info("End of test service")


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_image_selection(image, swarm, network, make_service):
    """Test that the spawner allows for dynamic image selection"""
    test_logger.info("Start of the image selection test")
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
        # login
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

        user_image = "ucphhpc/base-notebook:latest"
        user_image_name = "Basic Python Notebook"

        payload = {"name": user_image_name, "image": user_image}
        json_payload = json.dumps(payload)
        spawn_resp = s.post(
            JHUB_URL + "/hub/spawn/{}".format(username),
            files={
                "select_image": (
                    None,
                    json_payload,
                )
            },
        )

        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        target_service_name = "{}-{}-{}".format("jupyter", username, "1")
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Verify that a task is succesfully running
        running_task = wait_for_service_task(
            client, spawned_service, filters={"desired-state": "running"}, timeout=300
        )
        assert running_task

        # Verify that the image is correct
        service_image = get_task_image(running_task)
        assert service_image == user_image

        service_labels = get_service_labels(spawned_service)
        assert service_labels is not None
        assert service_labels["image_name"] == user_image_name

        # Delete the spawned service
        delete_headers = {"Referer": urljoin(JHUB_URL, "/hub/home"), "Origin": JHUB_URL}

        jhub_user = get_service_user(spawned_service)
        delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(jhub_user))

        deleted = delete(s, delete_url, headers=delete_headers)
        assert deleted

        deleted_service = get_service(client, target_service_name)
        assert deleted_service is None

        # Spawn a second service with a different name but the same image ##
        # Spawn a notebook
        second_spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        test_logger.info("Spawn page message: {}".format(second_spawn_form_resp.text))

        assert second_spawn_form_resp.status_code == 200
        assert "Select a notebook image" in second_spawn_form_resp.text

        second_image_name = "Basic Python Notebook 2"
        selection_payload = {"name": second_image_name, "image": user_image}
        json_second_payload = json.dumps(selection_payload)

        spawn_resp = s.post(
            JHUB_URL + "/hub/spawn/{}".format(username),
            files={
                "select_image": (
                    None,
                    json_second_payload,
                )
            },
        )
        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        second_target_service_name = "{}-{}-{}".format("jupyter", username, "1")
        second_spawned_service = get_service(client, second_target_service_name)
        assert second_spawned_service is not None

        # Verify that a task is succesfully running
        second_running_task = wait_for_service_task(
            client, second_spawned_service, filters={"desired-state": "running"}
        )
        assert second_running_task

        # Verify that the image is correct
        second_service_image = get_task_image(second_running_task)
        assert second_service_image == user_image

        second_service_labels = get_service_labels(second_spawned_service)
        assert second_service_labels is not None
        assert second_service_labels["image_name"] == second_image_name

        # Delete the second spawned service
        deleted = delete(s, delete_url, headers=delete_headers)
        assert deleted

        deleted_service = get_service(client, second_target_service_name)
        assert deleted_service is None
