import docker
import requests


# def test_creates_service(hub_service):
#     """Test that logging in as a new user creates a new docker service."""
#     client = docker.from_env()
#     # jupyterhub service should be running at this point
#     services_before_login = client.services.list()
#
#     # login
#     session = requests.session()
#     login_response = session.post(
#         "http://127.0.0.1:8000/hub/login?next=",
#         data={"username": "a-new-user",
#               "password": "just magnets"})
#     assert login_response.status_code == 200
#     # Spawn a new service
#     spawn_response = session.post("http://127.0.0.1:8000/hub/spawn")
#     assert spawn_response.status_code == 200
#
#     services_after_login = client.services.list()
#     assert len(services_after_login) - len(services_before_login) == 1
#
#     # Remove the service we just created,
#     # or we'll get errors when tearing down the fixtures
#     (set(services_after_login) - set(services_before_login)).pop().remove()


def test_create_mig_service(mig_service, mig_mount_target):
    """ Test that spawning a mig service works"""
    client = docker.from_env()
    services_before_login = client.services.list()
    session = requests.session()
    # Spawn before login -> foot in face
    spawn_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_resp.status_code == 403

    user_cert = '/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Rasmus ' \
                'Munk/emailAddress=rasmus.munk@nbi.ku.dk'
    # Auth header
    auth_header = {'Remote-User': user_cert}
    # login
    login_resp = session.get(
        "http://127.0.0.1:8000/hub/login", headers=auth_header
    )
    assert login_resp.status_code == 200

    # # Spawn a MiG mount container without having provided the MiG Mount header
    # spawn_no_mig_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    # assert 'missing MiG mount authentication keys, try reinitializing them ' \
    #        'through the MiG interface' in spawn_no_mig_resp.text
    # assert (len(client.services.list()) - len(services_before_login)) == 0

    spawn_resp = session.post("http://127.0.0.1:8000/hub/spawn")
    assert spawn_resp.status_code == 200

    # Remove the service we just created,
    # or we'll get errors when tearing down the fixtures
    #(set(services_after_login) - set(services_before_login)).pop().remove()

