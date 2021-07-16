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
    get_service,
    get_service_tasks,
    get_task_mounts,
    get_task_image,
    get_volume,
    get_service_url,
    get_service_api_url,
    get_service_user,
    wait_for_task_state,
    wait_for_site,
    delete_via_url,
)

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

# swarm config
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
    # Auth header
    test_logger.info("Authenticating with user: {}".format(username))
    auth_header = {"Remote-User": username}
    assert wait_for_site(JHUB_URL, valid_status_code=401) is True

    with requests.Session() as s:
        auth_url = urljoin(JHUB_URL, "/hub/home")
        login_response = s.get(auth_url, headers=auth_header)
        test_logger.info("Home response message: {}".format(login_response.text))
        assert login_response.status_code == 200

        private_key = ""
        # Extract mount target ssh private key
        for task in mount_target.tasks():
            if task["Status"]["State"] == "running":
                cont_id = task["Status"]["ContainerStatus"]["ContainerID"]
                cmd = "".join(["cat ", "/home/mountuser/.ssh/id_rsa"])
                container = client.containers.get(cont_id)
                private_key = container.exec_run(cmd)[1].decode("utf-8")
                break
        assert private_key != ""

        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        test_logger.info("Spawn page message: {}".format(spawn_form_resp.text))
        assert spawn_form_resp.status_code == 200
        assert "Select a notebook image" in spawn_form_resp.text
        user_image = "nielsbohr/base-notebook:latest"
        user_image_name = "Base Notebook"
        payload = {"select_image": [{"image": user_image, "name": user_image_name}]}
        json_payload = json.dumps(payload)

        target_user = "mountuser"
        ssh_host_target = socket.gethostname()
        mount_info = {
            "HOST": "DUMMY",
            "USERNAME": target_user,
            "PATH": "".join(["@", ssh_host_target, ":"]),
            "PRIVATEKEY": private_key,
        }
        mount_header = dict(Mount=str(mount_info))
        mount_header.update(auth_header)
        mount_resp = s.post(JHUB_URL + "/hub/data", headers=mount_header)
        test_logger.info("Hub Data response message: {}".format(mount_resp.text))
        assert mount_resp.status_code == 200
        spawn_resp = s.post(
            JHUB_URL + "/hub/spawn", data=json_payload, headers=mount_header
        )

        test_logger.info("Spawn POST response message: {}".format(spawn_resp.text))
        assert spawn_resp.status_code == 200

        post_spawn_services = list(
            set(client.services.list()) - set(services_before_spawn)
        )
        test_logger.info("Post spawn services: {}".format(post_spawn_services))
        # New services are there
        assert len(post_spawn_services) > 0

        # Get spawned service
        target_service_name = "{}-{}-{}".format("jupyter", username, "1")
        # jupyterhub_service = get_service(client, HUB_SERVICE_NAME)
        spawned_service = get_service(client, target_service_name)
        assert spawned_service is not None

        # Verify that a task is succesfully running
        task_state_found = wait_for_task_state(
            client, spawned_service, filters={"desired-state": "running"}
        )
        assert task_state_found is not False

        tasks = get_service_tasks(
            client, spawned_service, filters={"desired-state": "running"}
        )
        assert tasks is not None
        assert isinstance(tasks, list) is True
        assert len(tasks) == 1
        task = tasks[0]

        mount_volume_name = "sshvolume-user-{}".format(username)
        task_mounts = get_task_mounts(
            client, task, filters={"Source": mount_volume_name}
        )
        # Ensure it is using the correct driver
        for mount in task_mounts:
            assert (
                mount["VolumeOptions"]["DriverConfig"]["Name"]
                == "nielsbohr/sshfs:latest"
            )

        # Ensure it is the correct image
        service_image = get_task_image(task)
        assert service_image == user_image

        # Validate mounts
        test_logger.info("Current running jupyter services: {}".format(spawned_service))
        volume = get_volume(client, mount_volume_name)
        assert volume is not None

        # Get the service api url
        service_url = get_service_url(spawned_service)
        # If failed the service might not be running
        if not service_url:
            test_logger.info("Properly failed to start the service correctly")
        assert service_url is not None

        # Combine with the base jhub URL
        jhub_service_api = urljoin(JHUB_URL, service_url)
        # Wait for the site to be up and running
        assert wait_for_site(
            jhub_service_api,
            valid_status_code=200,
            auth_url=auth_url,
            auth_headers=auth_header,
            require_xsrf=True
        )

        # Write to user home
        new_file = "write_test.ipynb"
        data = json.dumps({"name": new_file})
        test_logger.info("Looking for xsrf in: {}".format(s.cookies))

        # Refresh csrf token
        assert wait_for_session(s, jhub_service_api)
        assert "_xsrf" in s.cookies
        xsrf_token = s.cookies["_xsrf"]
        service_api_url = get_service_api_url(spawned_service, postfix_url="contents/")
        jhub_service_content = urljoin(JHUB_URL, service_api_url)

        xsrf_headers = {"X-XSRFToken": xsrf_token}
        resp = s.put(
            "".join([jhub_service_content, new_file]),
            data=data,
            headers=xsrf_headers,
        )
        assert resp.status_code == 201

        # Remove via the web interface
        jhub_user = get_service_user(spawned_service)
        # Wait for the server to finish deleting
        delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(jhub_user))
        delete_headers = dict(Referer=JHUB_URL)
        delete_headers.update(xsrf_headers)

        assert (
            delete_via_url(
                delete_url,
                headers=delete_headers,
                auth_url=auth_url,
                auth_headers=auth_header,
            )
            is True
        )

        # double check it is gone
        notebook_volumes_after = [
            volume
            for volume in client.volumes.list()
            for service in notebook_services
            if volume.name.strip("sshvolume-user-") in service.name.strip("jupyter-")
        ]

        services_after_remove = client.services.list()
        assert len((set(services_before_spawn) - set(services_after_remove))) == 0
        assert len(notebook_volumes_after) == 0
        test_logger.info("End of mount service testing")
