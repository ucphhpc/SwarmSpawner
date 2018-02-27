import docker
import requests

def test_creates_service(hub_service):
    """Test that logging in as a new user creates a new docker service."""
    client = docker.from_env()
    # jupyterhub service should be running at this point
    services_before_login = client.services.list()

    # login
    session = requests.session()
    login_response = session.post(
        "http://127.0.0.1:8000/hub/login?next=",
                                   data={"username": "a-new-user",
                                         "password": "just magnets"})
    assert login_response.status_code == 200
    # Spawn a new service
    spawn_response = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_response.status_code == 200

    services_after_login = client.services.list()
    assert len(services_after_login) - len(services_before_login) == 1

    # Remove the service we just created, or we'll get errors when tearing down the fixtures
    (set(services_after_login) - set(services_before_login)).pop().remove()
