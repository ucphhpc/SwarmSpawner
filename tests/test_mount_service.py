import pytest
import docker
import requests
import logging
import json
import time
import socket
from urllib.parse import urljoin
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath
from util import (
    delete,
    put,
    get_service,
    get_task_mounts,
    get_task_image,
    get_volume,
    get_service_api_url,
    get_service_user,
    get_service_env,
    remove_volume,
    wait_for_session,
    wait_for_service_task,
    wait_for_service_msg,
    wait_for_site,
    wait_for_remove_volume,
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

# swarm config
# If the test host has multiple interfaces that the
# swarm can listen, use -> 'advertise_addr': 'host-ip'
swarm_config = {}
network_config = {
    "name": NETWORK_NAME,
    "driver": "overlay",
    "options": {"subnet": "192.168.0.0/24"},
    "attachable": True,
}

# hub config
hub_config = join(dirname(realpath(__file__)), "configs", "mount_jupyterhub_config.py")
hub_sshfs_service = {
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

mount_service = {
    "image": MOUNT_IMAGE_TAG,
    "name": MOUNT_SERVICE_NAME,
    "endpoint_spec": EndpointSpec(ports={2222: 22}),
}


@pytest.mark.parametrize("image", [hub_image], indirect=["image"])
@pytest.mark.parametrize("swarm", [swarm_config], indirect=["swarm"])
@pytest.mark.parametrize("network", [network_config], indirect=["network"])
def test_sshfs_mount_hub(image, swarm, network, make_service):
    """Test that spawning a jhub service works"""
    test_logger.info("Start of mount service testing")
    make_service(hub_sshfs_service)
    mount_target = make_service(mount_service)
    client = docker.from_env()
    services_before_spawn = client.services.list()
    test_logger.info("Pre test services: {}".format(services_before_spawn))

    # Both services should be running here
    for service in services_before_spawn:
        while service.tasks() and service.tasks()[0]["Status"]["State"] != "running":
            time.sleep(1)
            state = service.tasks()[0]["Status"]["State"]
            assert state != "failed"

    username = "testuser"
    # Wait for Jupyterhub is running
    assert wait_for_site(JHUB_URL, valid_status_code=401) is True

    mount_volume_name = "sshvolume-user-{}".format(username)
    # Ensure that the volume is not present to begin with
    existing_volume = get_volume(client, mount_volume_name)
    if existing_volume:
        assert remove_volume(client, mount_volume_name)

    with requests.Session() as s:
        # Refresh cookies
        s.get(JHUB_URL)

        # Login
        auth_header = {"Remote-User": username}
        login_response = s.post(
            urljoin(JHUB_URL, "/hub/login"),
            headers=auth_header,
            params={"_xsrf": s.cookies["_xsrf"]},
        )
        test_logger.info("Login response message: {}".format(login_response.text))
        assert login_response.status_code == 200

        auth_url = urljoin(JHUB_URL, "/hub/home")
        login_response = s.get(auth_url, headers=auth_header)
        test_logger.info("Home response message: {}".format(login_response.text))
        assert login_response.status_code == 200

        # Wait for the OpenSSH server to be ready
        assert wait_for_service_msg(
            client,
            MOUNT_SERVICE_NAME,
            msg="Running the OpenSSH Server",
            logs_kwargs={"stdout": True, "stderr": True},
        )

        private_key = ""
        # Extract mount target ssh private key
        for task in mount_target.tasks():
            if task["Status"]["State"] == "running":
                cont_id = task["Status"]["ContainerStatus"]["ContainerID"]
                cmd = "".join(["cat ", "/home/mountuser/.ssh/id_rsa"])
                container = client.containers.get(cont_id)
                private_key = container.exec_run(cmd)[1].decode("utf-8")
                break
        assert isinstance(private_key, str)
        assert private_key != ""
        assert "BEGIN RSA PRIVATE KEY" in private_key

        # Spawn a notebook
        spawn_form_resp = s.get(urljoin(JHUB_URL, "/hub/spawn"))
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))
        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text
        user_image = "ucphhpc/base-notebook:latest"
        user_image_name = "Base Notebook"
        payload = {"select_image": [{"image": user_image, "name": user_image_name}]}
        user_image_selection = json.dumps(payload)

        target_username = "mountuser"
        ssh_host_target = socket.gethostname()

        user_sshfs_mount_data = {
            "username": target_username,
            "targetHost": ssh_host_target,
            "targetPath": "",
            "privateKey": private_key,
            "port": 2222,
        }
        # Header values must be of str type
        user_mount_data = json.dumps({"mount_data": user_sshfs_mount_data})
        mount_resp = s.post(
            urljoin(JHUB_URL, "/hub/set-user-data"),
            data=user_mount_data,
            headers=auth_header,
            params={"_xsrf": s.cookies["_xsrf"]},
        )

        test_logger.info("Hub Data response message: {}".format(mount_resp.text))
        assert mount_resp.status_code == 200
        spawn_resp = s.post(
            urljoin(JHUB_URL, "/hub/spawn"),
            data=user_image_selection,
            headers=auth_header,
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

        # Retrieve the mounts
        task_mounts = get_task_mounts(
            client, running_task, filters={"Source": mount_volume_name}
        )
        # Ensure it is using the correct driver
        for mount in task_mounts:
            assert (
                mount["VolumeOptions"]["DriverConfig"]["Name"] == "ucphhpc/sshfs:latest"
            )

        # Ensure it is the correct image
        service_image = get_task_image(running_task)
        assert service_image == user_image

        # Validate mounts
        test_logger.info("Current running jupyter services: {}".format(spawned_service))
        volume = get_volume(client, mount_volume_name)
        assert volume is not None

        # Get the JupyterHub authentication token
        api_token = get_service_env(spawned_service, "JUPYTERHUB_API_TOKEN")
        assert api_token is not None

        # Get the service api url
        service_api_url = get_service_api_url(spawned_service)
        assert service_api_url is not None

        # Combine with the base jhub URL
        jhub_service_api_url = urljoin(JHUB_URL, f"{service_api_url}")
        assert wait_for_session(s, jhub_service_api_url, require_xsrf=True, timeout=300)
        jhub_service_api_content_url = urljoin(jhub_service_api_url, "contents/")

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
                "".join([jhub_service_api_content_url, new_file]),
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

        # Ensure that the volume is gone
        created_volume = get_volume(client, mount_volume_name)
        if created_volume:
            assert wait_for_remove_volume(client, mount_volume_name)
        test_logger.info("End of mount service testing")
