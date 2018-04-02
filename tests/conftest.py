"""Define fixtures for SwarmSpawner tests."""
import os
import time
import docker
import pytest
import sys
import socket
from docker.errors import NotFound

HUB_IMAGE_TAG = "hub:test"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"

CONFIG_TEMPLATE_PATH = "tests/jupyter_config.j2"


@pytest.fixture(scope='function')
def swarm():
    """Initialize the docker swarm that's going to run the servers
    as services.
    """
    client = docker.from_env()
    client.swarm.init(advertise_addr="192.168.99.100")
    yield client.swarm.attrs
    client.swarm.leave(force=True)


@pytest.fixture(scope='function')
def hub_image():
    """Build the image for the jupyterhub. We'll run this as a service
    that's going to then spawn the notebook server services.
    """
    client = docker.from_env()

    # Build the image from the root of the package
    parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    image = client.images.build(path=parent_dir, tag=HUB_IMAGE_TAG, rm=True,
                                pull=True)
    yield image
    image_obj = image[0]
    image_id = image_obj.id
    client.images.remove(image_obj.tags[0], force=True)

    removed = False
    while not removed:
        try:
            client.images.get(image_id)
        except docker.errors.NotFound:
            removed = True


@pytest.fixture(scope='function')
def network():
    """Create the overlay network that the hub and server services will
    use to communicate.
    """
    client = docker.from_env()
    network = client.networks.create(
        name=NETWORK_NAME,
        driver="overlay",
        options={"subnet": "192.168.0.0/20"},
        attachable=True
    )
    yield network
    network_id = network.id
    network.remove()
    removed = False
    while not removed:
        try:
            client.networks.get(network_id)
        except docker.errors.NotFound:
            removed = True


@pytest.fixture
def hub_service(hub_image, swarm, network):
    """Launch the hub service.
    Note that we don't directly use any of the arguments,
    but those fixtures need to be in place before we can launch the service.
    """
    client = docker.from_env()
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                               "jupyter_config.py")
    service = client.services.create(
        image=HUB_IMAGE_TAG,
        name=HUB_SERVICE_NAME,
        mounts=[
            ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
            ":".join(
                [config_path, "/srv/jupyterhub/jupyter_config.py", "ro"])],
        networks=[NETWORK_NAME],
        endpoint_spec=docker.types.EndpointSpec(ports={8000: 8000}))

    # Wait for the service's task to start running
    while service.tasks() and \
                    service.tasks()[0]["Status"]["State"] != "running":
        time.sleep(1)

    # And wait some more. This is...not great, but there seems to be
    # a period after the task is running but before the hub will accept
    # connections.
    # If the test code attempts to connect to the hub during that time,
    # it fails.
    time.sleep(10)

    yield service
    service_id = service.id
    service.remove()
    removed = False
    while not removed:
        try:
            client.services.get(service_id)
        except docker.errors.NotFound:
            removed = True


@pytest.fixture
def mig_service(hub_image, swarm, network):
    """Launch the hub service.
    Note that we don't directly use any of the arguments,
    but those fixtures need to be in place before we can launch the service.
    """
    client = docker.from_env()
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                               "mig_jupyter_config.py")
    service = client.services.create(
        image=HUB_IMAGE_TAG,
        name=HUB_SERVICE_NAME,
        mounts=[
            ":".join(["/var/run/docker.sock", "/var/run/docker.sock", "rw"]),
            ":".join(
                [config_path, "/srv/jupyterhub/jupyter_config.py", "ro"])],
        networks=[NETWORK_NAME],
        endpoint_spec=docker.types.EndpointSpec(ports={8000: 8000}),
        command=["jupyterhub", "-f", "/srv/jupyterhub/jupyter_config.py"]
    )
    while service.tasks() and \
                    service.tasks()[0]["Status"]["State"] != "running":
        time.sleep(1)

    # And wait some more. This is...not great, but there seems to be
    # a period after the task is running but before the hub will accept
    # connections.
    # If the test code attempts to connect to the hub during that time,
    # it fails.
    time.sleep(10)

    yield service
    service_id = service.id
    service.remove()
    removed = False
    while not removed:
        try:
            client.services.get(service_id)
        except docker.errors.NotFound:
            removed = True


@pytest.fixture
def mig_mount_target(swarm, network):
    """
    Sets up the host container that the notebook containers can mount
    """
    client = docker.from_env()
    services = client.services.list(filters={'name': HUB_SERVICE_NAME})
    # Make sure mig sshfs plugin is installed
    plugin = None
    try:
        plugin = client.plugins.get("rasmunk/sshfs")
    except NotFound:
        plugin = client.plugins.install("rasmunk/sshfs")
    finally:
        if not plugin.enabled:
            plugin.enable()

    assert len(services) == 1
    service_id = services[0].id
    containers = client.containers.list(
        filters={'label':
                 "com.docker.swarm.service.id={}".format(service_id)})

    attempts = 0
    while not len(containers) < 1 and attempts < 50:
        services = client.services.list(filters={'name': HUB_SERVICE_NAME})
        assert len(services) == 1
        service_id = services[0].id
        containers = client.containers.list(
            filters={'label':
                     "com.docker.swarm.service.id={}".format(service_id)})
        attempts += 1

    assert len(containers) == 1
    ip = containers[0].attrs['NetworkSettings']['Networks'][NETWORK_NAME][
        'IPAddress']

    args = "--hub-url=http://{}:8000".format(ip)
    docker_host = 'host.docker.internal'
    # default fqdn not supported on a linux host
    if sys.platform == 'linux':
        docker_host = socket.gethostname()

    service = client.services.create(
        image='nielsbohr/mig-mount-dummy',
        name='mig-dummy',
        networks=[NETWORK_NAME],
        endpoint_spec=docker.types.EndpointSpec(ports={2222: 22}),
        # The mig dummy mount target needs this, because the jupyterhub
        # service needs to know it should try sshfs mount via the host
        # because the mig_mount target service is exposed via the host and
        # therefore can't be reached via an internal mount.
        # This is done to avoid running the container in privileged mode
        # which is nessescary for fuse mount access
        env=["DOCKER_HOST=" + "{}".format(docker_host)],
        args=[args]
    )

    while service.tasks() and service.tasks()[0]["Status"]["State"] != \
            'running':
        time.sleep(1)
        state = service.tasks()[0]["Status"]["State"]
        assert state != 'failed'

    yield service
    service_id = service.id
    service.remove()
    removed = False
    while not removed:
        try:
            client.services.get(service_id)
        except docker.errors.NotFound:
            removed = True
