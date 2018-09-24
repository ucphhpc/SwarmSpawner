import docker
import time
import requests
import pytest
from random import SystemRandom
from docker.types import EndpointSpec
from os.path import dirname, join, realpath

HUB_IMAGE_TAG = "hub:test"
MOUNT_IMAGE_TAG = "nielsbohr/ssh-mount-dummy"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"
MOUNT_SERVICE_NAME = 'mount_target'

JHUB_URL = "http://127.0.0.1:8000"

rand_key = ''.join(SystemRandom().choice("0123456789abcdef") for _ in range(32))

# root dir
hub_path = dirname(dirname(__file__))
hub_image = {'path': hub_path, 'tag': HUB_IMAGE_TAG, 'rm': True, 'pull': False}


swarm_config = {'advertise_addr': '192.168.99.100'}
network_config = {'name': NETWORK_NAME, 'driver': 'overlay',
                  'options': {'subnet': '192.168.0.0/20'},
                  'attachable': True}
hub_config = join(dirname(realpath(__file__)), 'configs', 'jupyterhub_config.py')
hub_service = {'image': 'nielsbohr/jupyterhub:devel', 'name': HUB_SERVICE_NAME,
               'mounts': [
                   ':'.join(['/var/run/docker.sock', '/var/run/docker.sock', 'rw']),
                   ':'.join([hub_config, '/etc/jupyterhub/jupyterhub_config.py', 'ro'])
               ],
               'networks': [NETWORK_NAME],
               'endpoint_spec': EndpointSpec(ports={8000: 8000}),
               'command': ['jupyterhub', '-f', '/etc/jupyterhub/jupyterhub_config.py']}


@pytest.mark.parametrize('image', [hub_image], indirect=['image'])
@pytest.mark.parametrize('swarm', [swarm_config], indirect=['swarm'])
@pytest.mark.parametrize('network', [network_config], indirect=['network'])
def test_creates_service(image, swarm, network, make_service):
    """Test that logging in as a new user creates a new docker service."""
    make_service(hub_service)
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_spawn = client.services.list()

    with requests.Session() as s:
        ready = False
        while not ready:
            try:
                s.get(JHUB_URL)
                if s.get(JHUB_URL + "/hub/login").status_code == 200:
                    ready = True
            except requests.exceptions.ConnectionError:
                pass

        # login
        user = "a-new-user"
        login_response = s.post(JHUB_URL + "/hub/login?next=",
                                data={"username": user,
                                      "password": "just magnets"})
        assert login_response.status_code == 200
        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        assert spawn_form_resp.status_code == 200
        assert 'Select a notebook image' in spawn_form_resp.text
        payload = {
            'dockerimage': 'nielsbohr/base-notebook:latest'
        }
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload)
        assert spawn_resp.status_code == 200

        services = client.services.list()
        # New services are there
        assert len(services) > 0

        for service in services:
            while service.tasks() and \
                    service.tasks()[0]["Status"]["State"] != "running":
                time.sleep(1)
                state = service.tasks()[0]["Status"]["State"]
                assert state != 'failed'

        # wait for user home
        home_resp = s.get(JHUB_URL + "/user/{}/tree?".format(user))
        assert home_resp.status_code == 200

        # New services are there
        services_after_spawn = set(client.services.list()) - set(services_before_spawn)
        assert len(services_after_spawn) > 0

        # Remove via the web interface
        resp = s.delete(JHUB_URL + "/hub/api/users/{}/server".format(user),
                        headers={'Referer': '127.0.0.1:8000/hub/'})
        assert resp.status_code == 204
        # double check it is gone
        services_after_remove = client.services.list()
        assert len((set(services_before_spawn) - set(services_after_remove))) == 0
