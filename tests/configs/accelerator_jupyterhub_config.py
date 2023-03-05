from jhub.accelerators import AcceleratorPool, AcceleratorManager

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
mig_gpu_pool = AcceleratorPool(
    type="GPU",
    oversubscribe=False,
    mappings={
        "0": "MIG-1",
        "1": "MIG-2",
        "2": "MIG-3"
    },
)
c.SwarmSpawner.accelerator_manager = AcceleratorManager(
    {"mig_gpu_pool": mig_gpu_pool}
)

# Available docker images the user can spawn
c.SwarmSpawner.images = [
    {
        "image": "ucphhpc/gpu-notebook:latest",
        "name": "GPU Notebook",
        "accelerator_pools": ["mig_gpu_pool"],
    },
]
