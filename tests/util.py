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
    tasks = service.tasks(filters=filters)
    if not tasks:
        return None
    return tasks


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


def get_volume(client, volume_name, filters=None):
    if not filters:
        filters = {}
    volumes = client.volumes.list(filters=filters)
    return volumes


def get_service_prefix(service):
    # The prefix is located in the service environment variables
    envs = {}
    for env in service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"]["Env"]:
        key, value = env.split("=")
        envs[key] = value

    service_prefix = envs["JUPYTERHUB_SERVICE_PREFIX"]
    return service_prefix


def get_service_api_url(service, postfix_url=None):
    if not postfix_url:
        postfix_url = ""

    service_prefix = get_service_prefix(service)
    api_url = "{}/api/contents/{}".format(service_prefix, postfix_url)
    return api_url
