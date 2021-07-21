import docker
import time
import requests
from urllib.parse import urljoin


def get_service(client, service_name, filters=None):
    if not filters:
        filters = {"name": service_name}
    services = client.services.list(filters=filters)
    if not services:
        return None

    if len(services) != 1:
        return None
    return services[0]


def get_service_tasks(client, service, filters=None):
    if not filters:
        filters = {}
    try:
        return service.tasks(filters=filters)
    except docker.errors.NotFound:
        return None
    return None


def get_task_mounts(client, task, filters=None):
    task_mounts = task["Spec"]["ContainerSpec"]["Mounts"]
    if not task_mounts:
        return []

    if not filters:
        filters = {}

    mounts = []
    for mount in task_mounts:
        if filters:
            for key, attr in mount.items():
                if key in filters and filters[key] == attr:
                    mounts.append(mount)
        else:
            mounts.append(mount)
    return mounts


def get_task_image(task):
    return task["Spec"]["ContainerSpec"]["Image"]


def get_volume(client, volume_name, filters=None):
    if not filters:
        filters = {}
    volumes = client.volumes.list(filters=filters)
    for volume in volumes:
        if volume.name == volume_name:
            return volume
    return None


def remove_volume(client, volume_name):
    volume = get_volume(client, volume_name)
    if volume:
        return volume.remove()
    return False


def get_service_env(service, env_key=None):
    # If no Env, the service might not be started succesfully
    if "Env" not in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]:
        return None

    envs = {}
    for env in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"]:
        key, value = env.split("=")
        envs[key] = value

    if env_key and env_key in envs:
        return envs[env_key]
    return None


def get_service_prefix(service):
    # The prefix is located in the service environment variables
    return get_service_env(service, env_key="JUPYTERHUB_SERVICE_PREFIX")


def get_service_user(service):
    return get_service_env(service, env_key="JUPYTERHUB_USER")


def get_service_url(service, postfix_url=None):
    if not postfix_url:
        postfix_url = ""

    service_prefix = get_service_prefix(service)
    if not service_prefix:
        return None
    return service_prefix


def get_service_api_url(service, postfix_url=None):
    if not postfix_url:
        postfix_url = ""

    service_url = get_service_url(service)
    if not service_url:
        return None

    api_url = urljoin(service_url, "api/")
    if postfix_url:
        api_url = urljoin(api_url, postfix_url)
    return api_url


def wait_for_task_state(client, service, timeout=60, filters=None):
    attempts = 0
    while attempts < timeout:
        service_tasks = get_service_tasks(client, service, filters=filters)
        if get_service_tasks(client, service, filters=filters):
            return True
        attempts += 1
        time.sleep(1)
    return False


def get_session_csrf(session, url):
    try:
        resp = s.get(url)
    except requests.exceptions.ConnectionError:
        pass
    return False


def get_site(session, url, timeout=60, valid_status_code=200):
    num_attempts = 0
    while num_attempts < timeout:
        try:
            resp = session.get(url)
            if resp.status_code == valid_status_code:
                return True
        except requests.exceptions.ConnectionError:
            pass
        num_attempts += 1
        time.sleep(1)
    return False


# Waits for 5 minutes for a site to be ready
def wait_for_site(
    url,
    timeout=60,
    valid_status_code=200,
    auth_url=None,
    auth_headers=None,
    require_xsrf=False,
):
    with requests.Session() as s:
        if auth_url:
            auth_resp = s.get(auth_url, headers=auth_headers)
            if auth_resp.status_code != 200:
                return False
        if get_site(s, url, timeout=timeout, valid_status_code=valid_status_code):
            if require_xsrf:
                if "_xsrf" in s.cookies:
                    return True
            else:
                return True
    return False


def wait_for_session(
    session, url, timeout=60, valid_status_code=200, require_xsrf=False
):
    if get_site(session, url, timeout=timeout, valid_status_code=valid_status_code):
        if require_xsrf:
            if "_xsrf" in session.cookies:
                return True
        else:
            return True
    return False


def delete_via_url(
    url,
    headers=None,
    timeout=60,
    valid_status_code=204,
    auth_url=None,
    auth_headers=None,
    require_xsrf=False,
):
    if not headers:
        headers = {}

    attempts = 0
    with requests.Session() as s:
        # If authentication is required
        if auth_url:
            auth_resp = s.get(auth_url, headers=auth_headers)
            if auth_resp.status_code != 200:
                return False

        while attempts < timeout:
            resp = s.delete(url, headers=headers)
            if resp.status_code == valid_status_code:
                if require_xsrf:
                    if "_xsrf" in s.cookies:
                        return True
                else:
                    return True
            attempts += 1
            time.sleep(1)
    return False
