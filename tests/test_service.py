import docker
import requests
import pytest
from os.path import dirname, join, realpath

HUB_IMAGE_TAG = "hub:test"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"

CONFIG_TEMPLATE_PATH = "tests/jupyter_config.j2"
JHUB_URL = "http://127.0.0.1:8000"

# root dir
hub_path = dirname(dirname(__file__))
hub_image = {'path': hub_path, 'tag': HUB_IMAGE_TAG, 'rm': True, 'pull': False}

swarm_config = {'advertise_addr': '192.168.99.100'}
network_config = {'name': NETWORK_NAME, 'driver': 'overlay',
                  'options': {'subnet': '192.168.0.0/20'},
                  'attachable': True}
hub_config = join(dirname(realpath(__file__)), "jupyterhub_config.py")

hub_service = {'image': HUB_IMAGE_TAG, 'name': HUB_SERVICE_NAME,
               'mounts': [
                   ':'.join(['/var/run/docker.sock', '/var/run/docker.sock', 'rw']),
                   ':'.join([hub_config, '/etc/jupyterhub/jupyterhub_config.py', 'ro'])
               ],
               'networks': [NETWORK_NAME],
               'endpoint_spec': docker.types.EndpointSpec(ports={8000: 8000}),
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
            'dockerimage': 'jupyter/base-notebook:9f9e5ca8fe5a'
        }
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload)
        assert spawn_resp.status_code == 200

        # wait for user home
        home_resp = s.get(JHUB_URL + "/user/{}/?redirects=1".format(user))
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
        assert len((set(services_before_spawn) - set(services_after_remove))) \
            == 0


# def test_create_mig_service(mig_service):
#     """ Test that spawning a mig service works"""
#     client = docker.from_env()
#     services_before_spawn = client.services.list()
#
#     user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Rasmus ' \
#                 'Munk/emailAddress=rasmus.munk@nbi.ku.dk'
#     # Auth header
#     auth_header = {'Remote-User': user_cert}
#     # login
#     with requests.Session() as s:
#
#         login_resp = s.get(
#             jhub_url + "/hub/login", headers=auth_header
#         )
#         assert login_resp.status_code == 200
#
#         spawn_form_resp = s.get(jhub_url + "/hub/spawn")
#         image = 'nielsbohr/base-notebook:devel'
#         assert spawn_form_resp.status_code == 200
#         assert 'Select a notebook image' in spawn_form_resp.text
#         payload = {
#             'dockerimage': image
#         }
#         spawn_resp = s.post(jhub_url + "/hub/spawn", data=payload)
#         assert spawn_resp.status_code == 200
#
#         attempts = 0
#         spawned_services = set()
#         while not len(spawned_services) > 0 and attempts < 50:
#             services_after_spawn = client.services.list()
#             spawned_services = (set(services_after_spawn)
#                                 - set(services_before_spawn))
#             attempts += 1
#
#         # New services are there
#         assert len(spawned_services) > 0
#
#         for service in spawned_services:
#             while service.tasks() and \
#                             service.tasks()[0]["Status"][
#                                 "State"] != "running":
#                 time.sleep(1)
#                 state = service.tasks()[0]["Status"]["State"]
#                 assert state != 'failed'
#
#         # Validate the Spawned services
#         for service in spawned_services:
#             for task in service.tasks():
#                 assert task['Status']['State'] == 'running'
#                 # Correct image
#                 assert task['Spec']['ContainerSpec']['Image'] == image
#                 for mount in task['Spec']['ContainerSpec']['Mounts']:
#                     assert mount['VolumeOptions']['DriverConfig']['Name'] \
#                            == 'rasmunk/sshfs:latest'
#
#         # Remove the services we just created,
#         # or we'll get errors when tearing down the fixtures
#         spawned_services.pop().remove()


# TODO -> make test that validate use_user options

# TODO -> make test that spawns many default images

# TODO -> make test that validates different image spawn
