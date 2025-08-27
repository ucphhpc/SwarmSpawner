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


def get_service_tasks(client, service, filters=None, target_state="running"):
    if not filters:
        filters = {}
    try:
        tasks = service.tasks(filters=filters)
        return tasks
    except docker.errors.NotFound:
        pass
    return []


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
        try:
            volume.remove()
            return True
        except Exception:
            return False
    return True


def wait_for_remove_volume(client, volume_name, timeout=60):
    attempts = 0
    while attempts < timeout:
        removed = remove_volume(client, volume_name)
        if removed:
            return True
        attempts += 1
        time.sleep(1)
    return False


def get_service_env(service, env_key=None):
    # If no Env, the service might not be started succesfully
    if "Env" not in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]:
        return None

    envs = {}
    for env in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"]:
        key, value = env.split("=", 1)
        envs[key] = value

    if env_key and env_key in envs:
        return envs[env_key]
    return None


def get_service_labels(service, label_key=None):
    if "Labels" not in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]:
        return None

    labels = service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]["Labels"]
    if not label_key:
        return labels

    if label_key in labels:
        return labels[label_key]
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


def get_task_state(service_task):
    return service_task["Status"]["State"]


def wait_for_service_task(
    client, service, timeout=60, filters=None, target_state="running"
):
    attempts = 0
    while attempts < timeout:
        tasks = get_service_tasks(
            client, service, filters=filters, target_state=target_state
        )
        for task in tasks:
            task_state = get_task_state(task)
            if task_state == target_state:
                return task
        attempts += 1
        time.sleep(1)
    return None


def wait_for_service_msg(client, service, timeout=60, msg="", logs_kwargs=None):
    if not logs_kwargs:
        logs_kwargs = {}

    attempts = 0
    while attempts < timeout:
        logs = get_service(client, service).logs(**logs_kwargs)
        for log in logs:
            string_log = str(log)
            if msg in string_log:
                return True
        attempts += 1
        time.sleep(1)
    return False


def get_site(session, url, headers=None, valid_status_code=200):
    if not headers:
        headers = {}
    try:
        resp = session.get(url, headers=headers)
        if resp.status_code == valid_status_code:
            return True
    except requests.exceptions.ConnectionError:
        pass
    return False


# Waits for 5 minutes for a site to be ready
def _wait_for_site(
    session, url, headers=None, timeout=60, valid_status_code=200, require_xsrf=False
):
    attempts = 0
    while attempts < timeout:
        if get_site(session, url, headers=headers, valid_status_code=valid_status_code):
            if require_xsrf:
                if "_xsrf" in session.cookies:
                    return True
            else:
                return True
        attempts += 1
        time.sleep(1)
    return False


def wait_for_site(
    url,
    headers=None,
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

        if _wait_for_site(
            s,
            url,
            headers=headers,
            timeout=timeout,
            valid_status_code=valid_status_code,
            require_xsrf=require_xsrf,
        ):
            if require_xsrf:
                if "_xsrf" in s.cookies:
                    return True
            else:
                return True
    return False


def wait_for_session(
    session, url, timeout=60, valid_status_code=200, require_xsrf=False
):
    if _wait_for_site(
        session,
        url,
        timeout=timeout,
        valid_status_code=valid_status_code,
        require_xsrf=require_xsrf,
    ):
        if require_xsrf:
            if "_xsrf" in session.cookies:
                return True
        else:
            return True
    return False


def put(session, url, timeout=60, valid_status_code=201, **request_kwargs):
    attempts = 0
    while attempts < timeout:
        resp = session.put(url, **request_kwargs)
        if resp.status_code == valid_status_code:
            return True
        attempts += 1
        time.sleep(1)
    return False


def get(session, url, headers=None, valid_status_code=200, params=None):
    if not headers:
        headers = {}
    try:
        resp = session.get(url, headers=headers, params=params)
        if resp.status_code == valid_status_code:
            return resp
    except requests.exceptions.ConnectionError:
        pass
    return False


def delete(session, url, timeout=60, headers=None, valid_status_code=204, params=None):
    if not headers:
        headers = {}
    if not params:
        params = {}

    attempts = 0
    while attempts < timeout:
        resp = session.delete(url, headers=headers, params=params)
        if resp.status_code == valid_status_code:
            return True
        attempts += 1
        time.sleep(1)
    return False


def refresh_csrf(session, url, timeout=60, headers=None):
    if not headers:
        headers = {}
    return wait_for_session(session, url, timeout=timeout, require_xsrf=True)


def load(path, mode="r", readlines=False):
    try:
        with open(path, mode) as fh:
            if readlines:
                return fh.readlines()
            return fh.read()
    except Exception as err:
        print("Failed to load file: {} - {}".format(path, err))
    return False
