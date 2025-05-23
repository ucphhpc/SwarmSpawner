import pytest
import docker
import requests
import logging
import json
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath
from urllib.parse import urljoin
from util import (
    wait_for_site,
    wait_for_session,
    delete,
    put,
    get_service_api_url,
    get_service,
    get_service_user,
    get_service_env,
    wait_for_service_task,
)


HUB_IMAGE_TAG = "hub:test"
MOUNT_IMAGE_TAG = "ucphhpc/ssh-mount-dummy"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"
MOUNT_SERVICE_NAME = "mount_target"
TEST_SUBNET = "192.168.99.0/24"
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
    "options": {"subnet": TEST_SUBNET},
    "attachable": True,
}
remote_hub_config = join(
    dirname(realpath(__file__)), "configs", "remote_auth_jupyterhub_config.py"
)
remote_hub_service = {
    "image": HUB_IMAGE_TAG,
    "name": HUB_SERVICE_NAME,
    "mounts": [
        ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
        ":".join([remote_hub_config, "/etc/jupyterhub/jupyterhub_config.py", "ro"]),
    ],
    "networks": [NETWORK_NAME],
    "endpoint_spec": EndpointSpec(ports={PORT: PORT}),
    "env": ["JUPYTERHUB_CRYPT_KEY=" + rand_key],
    "command": ["jupyterhub", "-f", "/etc/jupyterhub/jupyterhub_config.py"],
}


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_remote_auth_hub(image, swarm, network, make_service):
    """Test that logging in as a new user creates a new docker service."""
    test_logger.info("Start of service testing")
    make_service(remote_hub_service)
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_spawn = client.services.list()
    test_logger.info("Pre test services: {}".format(services_before_spawn))
    username = "i-am-a-jupyter-user"

    # Auth header
    test_logger.info("Authenticating with user: {}".format(username))
    headers = {"Remote-User": username}
    assert wait_for_site(JHUB_URL, valid_status_code=401) is True

    with requests.Session() as s:
        # Refresh cookies
        s.get(JHUB_URL)

        # Login
        login_response = s.post(
            urljoin(JHUB_URL, "/hub/login"),
            headers=headers,
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

        # Get spawned service
        target_service_name = "{}-".format("jupyter")
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Wait for the spawned service to be running
        running_task = wait_for_service_task(
            client, spawned_service, filters={"desired-state": "running"}, timeout=300
        )
        assert running_task

        api_token = get_service_env(spawned_service, "JUPYTERHUB_API_TOKEN")
        assert api_token is not None

        service_api_url = get_service_api_url(spawned_service)
        assert service_api_url is not None

        # Combine with the base jhub URL
        jhub_service_api_url = urljoin(JHUB_URL, f"{service_api_url}")
        assert wait_for_session(s, jhub_service_api_url, require_xsrf=True, timeout=300)
        jub_service_api_content_url = urljoin(jhub_service_api_url, "contents/")

        # Write to user home
        new_file = "write_test.ipynb"
        data = json.dumps({"name": new_file})
        test_logger.info("Looking for xsrf in: {}".format(s.cookies))
        assert "_xsrf" in s.cookies
        # Jupyter expects colon seperated cookie value
        cookies = ";".join([f"{key}={value}" for key, value in dict(s.cookies).items()])

        # Write to home
        xsrf_headers = {
            "Authorization": f"token {api_token}",
            "X-Xsrftoken": s.cookies["_xsrf"],
            "Cookie": cookies,
        }
        # https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html#put--api-contents-path
        assert (
            put(
                s,
                "".join([jub_service_api_content_url, new_file]),
                headers=xsrf_headers,
                data=data,
            )
            is True
        )

        # Remove via the web interface
        assert "_xsrf" in s.cookies
        delete_headers = {
            "Referer": urljoin(JHUB_URL, "/hub/home"),
            "Origin": JHUB_URL,
        }

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

        deleted_service = get_service(client, target_service_name)
        assert deleted_service is None


custom_remote_hub_config = join(
    dirname(realpath(__file__)),
    "configs",
    "remote_auth_custom_username_jupyterhub_config.py",
)
custom_remote_hub_service = {
    "image": HUB_IMAGE_TAG,
    "name": HUB_SERVICE_NAME,
    "mounts": [
        ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
        ":".join(
            [custom_remote_hub_config, "/etc/jupyterhub/jupyterhub_config.py", "ro"]
        ),
    ],
    "networks": [NETWORK_NAME],
    "endpoint_spec": EndpointSpec(ports={PORT: PORT}),
    "env": ["JUPYTERHUB_CRYPT_KEY=" + rand_key],
    "command": ["jupyterhub", "-f", "/etc/jupyterhub/jupyterhub_config.py"],
}


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_remote_auth_hub_custom_username(image, swarm, network, make_service):
    """Test that logging in as a new user creates a new docker service."""
    test_logger.info("Start of service testing")
    make_service(custom_remote_hub_service)
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_spawn = client.services.list()
    test_logger.info("Pre test services: {}".format(services_before_spawn))
    username = "/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Name/emailAddress=mail@sdfsf.com"

    # Auth header
    test_logger.info("Authenticating with user: {}".format(username))
    headers = {"Remote-User": username}
    assert wait_for_site(JHUB_URL, valid_status_code=401) is True

    with requests.Session() as s:
        # Refresh cookies
        s.get(JHUB_URL)

        # Login
        login_response = s.post(
            urljoin(JHUB_URL, "/hub/login"),
            headers=headers,
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

        # Get spawned service
        target_service_name = "{}-".format("jupyter")
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Wait for the spawned service to be running
        running_task = wait_for_service_task(
            client, spawned_service, filters={"desired-state": "running"}, timeout=300
        )
        assert running_task

        api_token = get_service_env(spawned_service, "JUPYTERHUB_API_TOKEN")
        assert api_token is not None

        service_api_url = get_service_api_url(spawned_service)
        assert service_api_url is not None

        # Combine with the base jhub URL
        jhub_service_api_url = urljoin(JHUB_URL, f"{service_api_url}")
        assert wait_for_session(s, jhub_service_api_url, require_xsrf=True, timeout=300)
        jub_service_api_content_url = urljoin(jhub_service_api_url, "contents/")

        # Write to user home
        new_file = "write_test.ipynb"
        data = json.dumps({"name": new_file})
        test_logger.info("Looking for xsrf in: {}".format(s.cookies))
        assert "_xsrf" in s.cookies
        # Jupyter expects colon seperated cookie value
        cookies = ";".join([f"{key}={value}" for key, value in dict(s.cookies).items()])

        # Write to home
        xsrf_headers = {
            "Authorization": f"token {api_token}",
            "X-Xsrftoken": s.cookies["_xsrf"],
            "Cookie": cookies,
        }
        # https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html#put--api-contents-path
        assert (
            put(
                s,
                "".join([jub_service_api_content_url, new_file]),
                headers=xsrf_headers,
                data=data,
            )
            is True
        )

        # Remove via the web interface
        assert "_xsrf" in s.cookies
        delete_headers = {
            "Referer": urljoin(JHUB_URL, "/hub/home"),
            "Origin": JHUB_URL,
        }

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

        deleted_service = get_service(client, target_service_name)
        assert deleted_service is None
