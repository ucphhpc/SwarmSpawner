import docker
import requests
import time

jhub_url = "http://127.0.0.1:8000"


def test_creates_service(hub_service):
    """Test that logging in as a new user creates a new docker service."""
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_login = client.services.list()

    with requests.Session() as session:
        # login
        login_response = session.post(
            "http://127.0.0.1:8000/hub/login?next=",
            data={"username": "a-new-user",
                  "password": "just magnets"})
        assert login_response.status_code == 200
        # Spawn a notebook
        spawn_form_resp = session.get(jhub_url + "/hub/spawn")
        assert spawn_form_resp.status_code == 200
        assert 'Select a notebook image' in spawn_form_resp.text
        payload = {
            'dockerimage': 'jupyter/base-notebook:30f16d52126f'
        }
        spawn_resp = session.post(jhub_url + "/hub/spawn", data=payload)
        assert spawn_resp.status_code == 200

        services_after_login = client.services.list()
        assert len(services_after_login) - len(services_before_login) == 1

        # Remove the service we just created,
        # or we'll get errors when tearing down the fixtures
        (set(services_after_login) - set(services_before_login)).pop().remove()


def test_create_mig_service(mig_service, mig_mount_target):
    """ Test that spawning a mig service works"""
    client = docker.from_env()
    services_before_spawn = client.services.list()

    user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Rasmus ' \
                'Munk/emailAddress=rasmus.munk@nbi.ku.dk'
    # Auth header
    auth_header = {'Remote-User': user_cert}
    # login
    with requests.Session() as s:

        login_resp = s.get(
            jhub_url + "/hub/login", headers=auth_header
        )
        assert login_resp.status_code == 200

        spawn_form_resp = s.get(jhub_url + "/hub/spawn")
        assert spawn_form_resp.status_code == 200
        assert 'Select a notebook image' in spawn_form_resp.text
        payload = {
            'dockerimage': 'nielsbohr/base-notebook:devel'
        }
        spawn_resp = s.post(jhub_url + "/hub/spawn", data=payload)
        assert spawn_resp.status_code == 200

        attempts = 0
        spawned_services = set()
        while not len(spawned_services) > 0 and attempts < 50:
            services_after_spawn = client.services.list()
            spawned_services = (set(services_after_spawn)
                                - set(services_before_spawn))
            attempts += 1

        # New services are there
        assert len(spawned_services) > 0

        # If error, check whether the images is being pulled from the repo
        # If so wait of it
        # Wait for possible image pull
        if 'Error: HTTP 500: Internal Server Error' in spawn_resp.text:
            for service in spawned_services:
                while service.tasks() and \
                                service.tasks()[0]["Status"][
                                    "State"] != "running":
                    time.sleep(1)
                    state = service.tasks()[0]["Status"]["State"]
                    assert state != 'failed'

        # Validate the Spawned services
        for service in spawned_services:
            for task in service.tasks():
                assert task['Status']['State'] == 'running'
                for mount in task['Spec']['ContainerSpec']['Mounts']:
                    assert mount['VolumeOptions']['DriverConfig']['Name'] \
                           == 'rasmunk/sshfs:latest'
        # Remove the services we just created,

        # or we'll get errors when tearing down the fixtures

        spawned_services.pop().remove()



# TODO -> make test that validate use_user options

# TODO -> make test that spawns many default images

# TODO -> make test that validates different image spawn
