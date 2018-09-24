import pytest
import docker
import requests
import json
import time
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
hub_service = {'image': HUB_IMAGE_TAG, 'name': HUB_SERVICE_NAME,
               'mounts': [
                   ':'.join(['/var/run/docker.sock', '/var/run/docker.sock', 'rw']),
                   ':'.join([hub_config, '/etc/jupyterhub/jupyterhub_config.py', 'ro'])
               ],
               'networks': [NETWORK_NAME],
               'endpoint_spec': EndpointSpec(ports={8000: 8000}),
               'command': ['jupyterhub', '-f', '/etc/jupyterhub/jupyterhub_config.py']}

remote_hub_config = join(dirname(realpath(__file__)), 'configs',
                         'remote_auth_jupyterhub_config.py')
remote_hub_service = {'image': HUB_IMAGE_TAG, 'name': HUB_SERVICE_NAME,
                      'mounts': [
                          ':'.join(
                              ['/var/run/docker.sock', '/var/run/docker.sock', 'rw']),
                          ':'.join(
                              [remote_hub_config, '/etc/jupyterhub/jupyterhub_config.py',
                               'ro'])
                      ],
                      'networks': [NETWORK_NAME],
                      'endpoint_spec': EndpointSpec(ports={8000: 8000}),
                      'env': ['JUPYTERHUB_CRYPT_KEY=' + rand_key],
                      'command': ['jupyterhub', '-f',
                                  '/etc/jupyterhub/jupyterhub_config.py']}


@pytest.mark.parametrize('image', [hub_image], indirect=['image'])
@pytest.mark.parametrize('swarm', [swarm_config], indirect=['swarm'])
@pytest.mark.parametrize('network', [network_config], indirect=['network'])
def test_remote_auth_hub(image, swarm, network, make_service):
    """Test that logging in as a new user creates a new docker service."""
    make_service(remote_hub_service)
    client = docker.from_env()
    # Jupyterhub service should be running at this point
    services_before_spawn = client.services.list()

    user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Name' \
                '/emailAddress=mail@sdfsf.com'
    # Auth header
    headers = {'Remote-User': user_cert}
    with requests.Session() as s:
        ready = False
        while not ready:
            try:
                s.get(JHUB_URL)
                if s.get(JHUB_URL + "/hub/login").status_code == 401:
                    ready = True
            except requests.exceptions.ConnectionError:
                pass

        # Login
        login_response = s.post(JHUB_URL + "/hub/login", headers=headers)
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

        # New services are there
        post_spawn_services = list(set(client.services.list()) -
                                   set(services_before_spawn))
        assert len(post_spawn_services) > 0

        for service in post_spawn_services:
            while service.tasks() and \
                    service.tasks()[0]["Status"][
                        "State"] != "running":
                time.sleep(1)
                state = service.tasks()[0]["Status"]["State"]
                assert state != 'failed'

        # Notebook ids
        notebook_services = [service for service in post_spawn_services
                             if "jupyter-" in service.name]

        # Wait for user home
        for notebook_service in notebook_services:
            envs = {}
            for env in notebook_service.attrs['Spec']['TaskTemplate'][
                    'ContainerSpec']['Env']:
                key, value = env.split('=')
                envs[key] = value
            service_prefix = envs['JUPYTERHUB_SERVICE_PREFIX']
            home_resp = s.get(JHUB_URL + service_prefix)
            assert home_resp.status_code == 200

            # Write to user home
            hub_api_url = "{}/api/contents/".format(service_prefix)
            new_file = 'write_test.ipynb'
            data = json.dumps({'name': new_file})
            notebook_headers = {'X-XSRFToken': s.cookies['_xsrf']}
            resp = s.put(''.join([JHUB_URL, hub_api_url, new_file]), data=data,
                         headers=notebook_headers)
            assert resp.status_code == 201

            # Remove via the web interface
            jhub_user = envs['JUPYTERHUB_USER']
            resp = s.delete(JHUB_URL + "/hub/api/users/{}/server".format(jhub_user),
                            headers={'Referer': '127.0.0.1:8000/hub/'})
            assert resp.status_code == 204
        # double check it is gone
        services_after_remove = client.services.list()
        assert len((set(services_before_spawn) - set(services_after_remove))) == 0
