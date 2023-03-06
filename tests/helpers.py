import docker
import json
from urllib.parse import urljoin
from tests.util import get_service, delete, wait_for_service_task
from tests.defaults import JHUB_URL


def login(session, username, password):
    login_response = session.post(
        urljoin(JHUB_URL, "/hub/login"),
        data={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    return login_response


def spawn_notebook(session, username, image_name, image_data, valid_return_code=200):
    spawn_form_resp = session.get(JHUB_URL + "/hub/spawn")
    assert spawn_form_resp.status_code == 200
    assert "Select a notebook image" in spawn_form_resp.text

    payload = {"select_image": json.dumps({"name": image_name, "image": image_data})}
    spawn_resp = session.post(JHUB_URL + "/hub/spawn", data=payload)
    assert spawn_resp.status_code == valid_return_code
    return spawn_resp


def get_running_notebook(username):
    client = docker.from_env()
    target_service_name = "{}-{}-{}".format("jupyter", username, "1")
    running_notebook = get_service(client, target_service_name)
    return running_notebook


def stop_notebook(session, username):
    delete_headers = {"Referer": urljoin(JHUB_URL, "/hub/home"), "Origin": JHUB_URL}
    delete_url = urljoin(JHUB_URL, "/hub/api/users/{}/server".format(username))
    deleted = delete(session, delete_url, headers=delete_headers)
    return deleted


def wait_for_notebook(session, notebook, timeout=300):
    client = docker.from_env()
    # Verify that a task is succesfully running
    running_task = wait_for_service_task(
        client, notebook, filters={"desired-state": "running"}, timeout=timeout
    )
    return running_task
