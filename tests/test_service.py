import docker
import time
import requests
import logging
import pytest
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath

HUB_IMAGE_TAG = "hub:test"
MOUNT_IMAGE_TAG = "nielsbohr/ssh-mount-dummy"
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

    # Try for 5 minutes
    num_attempts = 0
    max_attempts = 60
    with requests.Session() as s:
        ready = False
        while not ready:
            if num_attempts > max_attempts:
                raise RuntimeError(
                    "Failed to connect to the JupyterHub login page within: {}".format(
                        5 * max_attempts / 60
                    )
                )
            try:
                print("Trying to connect to: {}".format(JHUB_URL))
                resp = s.get(JHUB_URL)
                if resp.status_code == 200:
                    ready = True
                else:
                    print(resp)
            except requests.exceptions.ConnectionError:
                pass
            num_attempts += 1
            time.sleep(5)

        # login
        user = "a-new-user"
        test_logger.info("Authenticating with user: {}".format(user))
        login_response = s.post(
            JHUB_URL + "/hub/login?next=",
            data={"username": user, "password": "just magnets"},
        )
        test_logger.info("Login response message: {}".format(login_response.text))
        assert login_response.status_code == 200
        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))
        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text
        payload = {"dockerimage": "nielsbohr/base-notebook:latest"}
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload)
        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        services = client.services.list()
        test_logger.info("Post spawn services: {}".format(services))
        # New services are there
        assert len(services) > 0

        for service in services:
            while (
                service.tasks() and service.tasks()[0]["Status"]["State"] != "running"
            ):
                time.sleep(1)
                state = service.tasks()[0]["Status"]["State"]
                assert state != "failed"

        # wait for user home
        home_resp = s.get(JHUB_URL + "/user/{}/tree?".format(user))
        assert home_resp.status_code == 200

        # New services are there
        services_after_spawn = set(client.services.list()) - set(services_before_spawn)
        assert len(services_after_spawn) > 0

        # Remove via the web interface
        # Wait for the server to finish spawning
        pending = True
        num_wait, max_wait = 0, 15
        while pending or num_wait > max_wait:
            num_wait += 1
            resp = s.delete(
                JHUB_URL + "/hub/api/users/{}/server".format(user),
                headers={"Referer": "127.0.0.1:{}/hub/".format(PORT)},
            )
            test_logger.info(
                "Response from removing the user server: {}".format(resp.text)
            )
            if resp.status_code == 204:
                pending = False
            time.sleep(1)

        assert resp.status_code == 204
        # double check it is gone
        services_after_remove = client.services.list()
        assert len((set(services_before_spawn) - set(services_after_remove))) == 0
        test_logger.info("End of test service")
