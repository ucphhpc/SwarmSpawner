"""Define fixtures for SwarmSpawner tests."""

import time
import docker
import pytest
from docker.errors import NotFound


HUB_IMAGE_TAG = "hub:test"
NETWORK_NAME = "jh_test"
HUB_SERVICE_NAME = "jupyterhub"
CONFIG_TEMPLATE_PATH = "tests/jupyter_config.j2"


@pytest.fixture(scope="function")
def swarm(request):
    """Initialize the docker swarm that's going to run the servers
    as services.
    """
    client = docker.from_env()
    client.swarm.init(**request.param)
    yield client.swarm.attrs
    client.swarm.leave(force=True)


@pytest.fixture(scope="function")
def network(request):
    """Create the overlay network that the hub and server services will
    use to communicate.
    """
    client = docker.from_env()
    _network = client.networks.create(**request.param)
    yield _network
    _network.remove()
    removed = False
    while not removed:
        try:
            client.networks.get(_network.id)
        except NotFound:
            removed = True


@pytest.fixture(scope="function")
def pull_image(request):
    client = docker.from_env()
    _image = client.images.pull(**request.param)
    yield _image

    image_obj = _image[0]
    image_id = image_obj.id
    client.images.remove(image_obj.tags[0], force=True)

    removed = False
    while not removed:
        try:
            client.images.get(image_id)
        except NotFound:
            removed = True


@pytest.fixture(scope="function")
def image(request):
    client = docker.from_env()
    _image = client.images.build(**request.param)
    yield _image

    image_obj = _image[0]
    image_id = image_obj.id
    client.images.remove(image_obj.tags[0], force=True)

    removed = False
    while not removed:
        try:
            client.images.get(image_id)
        except NotFound:
            removed = True


@pytest.fixture(name="make_container")
def make_container_():
    created = []
    client = docker.from_env()

    def make_container(options):
        _container = client.containers.run(**options)
        while _container.status != "running":
            time.sleep(1)
            _container = client.containers.get(_container.name)
        created.append(_container)
        return _container

    yield make_container

    for c in created:
        assert hasattr(c, "id")
        c.stop()
        c.wait()
        c.remove()
        removed = False
        while not removed:
            try:
                client.containers.get(c.id)
            except NotFound:
                removed = True


@pytest.fixture(name="make_service")
def make_service_():
    created = []
    client = docker.from_env()

    def make_service(options):
        _service = client.services.create(**options)
        while "running" not in [task["Status"]["State"] for task in _service.tasks()]:
            time.sleep(1)
            _service = client.services.get(_service.id)
        created.append(_service)
        return _service

    yield make_service

    for c in created:
        assert hasattr(c, "id")
        c.remove()
        removed = False
        while not removed:
            try:
                client.services.get(c.id)
            except NotFound:
                removed = True


@pytest.fixture(name="make_volume")
def make_volume_():
    created = []
    client = docker.from_env()

    def make_volume(options):
        _volume = client.volumes.create(options)
        created.append(_volume)
        return _volume

    yield make_volume

    for c in created:
        _id = c.id
        c.remove()
        removed = False
        while not removed:
            try:
                client.volumes.get(_id)
            except NotFound:
                removed = True
