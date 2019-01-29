import pytest
import docker
import requests
import json
import time
import socket
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

# swarm config
swarm_config = {'advertise_addr': '192.168.99.100'}
network_config = {'name': NETWORK_NAME, 'driver': 'overlay',
                  'options': {'subnet': '192.168.0.0/20'},
                  'attachable': True}

# hub config
hub_config = join(dirname(realpath(__file__)), 'configs', 'mount_jupyterhub_config.py')
hub_sshfs_service = {'image': HUB_IMAGE_TAG, 'name': HUB_SERVICE_NAME,
                     'mounts': [
                         ':'.join(['/var/run/docker.sock',
                                   '/var/run/docker.sock', 'rw']),
                         ':'.join([hub_config,
                                   '/etc/jupyterhub/jupyterhub_config.py',
                                   'ro'])
                     ],
                     'networks': [NETWORK_NAME],
                     'endpoint_spec': EndpointSpec(ports={8000: 8000}),
                     'env': ['JUPYTERHUB_CRYPT_KEY=' + rand_key],
                     'command': ['jupyterhub', '-f',
                                 '/etc/jupyterhub/jupyterhub_config.py']}

mount_service = {'image': MOUNT_IMAGE_TAG, 'name': MOUNT_SERVICE_NAME,
                 'endpoint_spec': EndpointSpec(ports={2222: 22})}


@pytest.mark.parametrize('image', [hub_image], indirect=['image'])
@pytest.mark.parametrize('swarm', [swarm_config], indirect=['swarm'])
@pytest.mark.parametrize('network', [network_config], indirect=['network'])
def test_sshfs_mount_hub(image, swarm, network, make_service):
    """ Test that spawning a jhub service works"""
    make_service(hub_sshfs_service)
    mount_target = make_service(mount_service)
    client = docker.from_env()
    services_before_spawn = client.services.list()
    # Both services should be running here
    for service in services_before_spawn:
        while service.tasks() and \
                service.tasks()[0]["Status"][
                    "State"] != "running":
            time.sleep(1)
            state = service.tasks()[0]["Status"]["State"]
            assert state != 'failed'

    user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Name' \
                '/emailAddress=mail@sdfsf.com'
    # Auth header
    headers = {'Remote-User': user_cert}
    with requests.Session() as s:
        ready = False
        # make sure jhub http service is up
        while not ready:
            try:
                s.get(JHUB_URL)
                if s.get(JHUB_URL + "/hub/home").status_code == 401:
                    ready = True
            except requests.exceptions.ConnectionError:
                pass

        login_response = s.get(JHUB_URL + "/hub/home", headers=headers)
        assert login_response.status_code == 200

        private_key = ''
        # Extract mount target ssh private key
        for task in mount_target.tasks():
            if task['Status']['State'] == 'running':
                cont_id = task['Status']['ContainerStatus']['ContainerID']
                cmd = ''.join(['cat ', '/home/mountuser/.ssh/id_rsa'])
                container = client.containers.get(cont_id)
                private_key = container.exec_run(cmd)[1].decode('utf-8')
                break
        assert private_key != ''

        # Spawn a notebook
        spawn_form_resp = s.get(JHUB_URL + "/hub/spawn")
        assert spawn_form_resp.status_code == 200
        assert 'Select a notebook image' in spawn_form_resp.text
        payload = {
            'dockerimage': 'nielsbohr/base-notebook:latest'
        }

        target_user = 'mountuser'
        ssh_host_target = socket.gethostname()
        mount_info = {'HOST': 'DUMMY', 'USERNAME': target_user,
                      'PATH': ''.join(['@', ssh_host_target, ':']),
                      'PRIVATEKEY': private_key}
        headers.update({'Mount': str(mount_info)})
        mount_resp = s.post(JHUB_URL + "/hub/data", headers=headers)
        assert mount_resp.status_code == 200
        spawn_resp = s.post(JHUB_URL + "/hub/spawn", data=payload, headers=headers)
        assert spawn_resp.status_code == 200

        post_spawn_services = list(set(client.services.list()) - set(
            services_before_spawn))
        # New services are there
        assert len(post_spawn_services) > 0

        # All should be running at this point
        for service in post_spawn_services:
            while service.tasks() and \
                    service.tasks()[0]["Status"]["State"] != "running":
                time.sleep(1)
                state = service.tasks()[0]["Status"]["State"]
                assert state != 'failed'

        # Validate mounts
        for service in post_spawn_services:
            for task in service.tasks():
                # Correct image
                if task['Spec']['ContainerSpec']['Image'] == image:
                    # Validate mount
                    assert task['Status']['State'] == 'running'
                    for mount in task['Spec']['ContainerSpec']['Mounts']:
                        assert mount['VolumeOptions']['DriverConfig']['Name'] \
                            == 'rasmunk/sshfs:latest'
        # Notebook ids
        notebook_services = [service for service in post_spawn_services
                             if "jupyter-" in service.name]
        assert len(notebook_services) > 0

        notebook_volumes = [volume for volume in client.volumes.list()
                            for service in notebook_services
                            if volume.name.strip('sshvolume-user-')
                            in service.name.strip('jupyter-')]

        assert len(notebook_volumes) > 0

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
        notebook_volumes_after = [volume for volume in client.volumes.list()
                                  for service in notebook_services
                                  if volume.name.strip('sshvolume-user-')
                                  in service.name.strip('jupyter-')]

        services_after_remove = client.services.list()
        assert len((set(services_before_spawn) - set(services_after_remove))) == 0
        assert len(notebook_volumes_after) == 0
