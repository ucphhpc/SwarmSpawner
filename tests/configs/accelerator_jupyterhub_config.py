from jhub.accelerators import AcceleratorPool

c = get_config()

c.JupyterHub.ip = "0.0.0.0"
c.JupyterHub.hub_ip = "0.0.0.0"

# Authenticator
c.JupyterHub.authenticator_class = "jhubauthenticators.DummyAuthenticator"
c.DummyAuthenticator.password = "just magnets"

c.JupyterHub.spawner_class = "jhub.SwarmSpawner"

# First pulls can be really slow, so let's give it a big timeout
c.SwarmSpawner.start_timeout = 60 * 15

c.SwarmSpawner.jupyterhub_service_name = "jupyterhub"

c.SwarmSpawner.networks = ["jh_test"]

# Accelerator setup
c.SwarmSpawner.enable_accelerator_system = True
c.SwarmSpawner.accelerator_pools = [
    AcceleratorPool(type="GPU", mappings={"NVIDIA-GPU": "0", "NVIDIA-GPU": "1"}),
]

# Available docker images the user can spawn
c.SwarmSpawner.images = [
    {"image": "ucphhpc/base-notebook:latest", "name": "Basic Python Notebook"},
    {"image": "ucphhpc/base-notebook:latest", "name": "Basic Python Notebook 2"},
    {
        "image": "ucphhpc/gpu-notebook:latest",
        "name": "GPU Notebook",
        "accelerator_pools": [gpu_accelerator_pool],
    },
]
