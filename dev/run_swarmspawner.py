import os
from jupyterhub.app import JupyterHub


if __name__ == "__main__":
    dev_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(dev_dir, "jupyterhub_config.py")
    JupyterHub.config_file = config_file
    # /home/rasmunk/repos/SwarmSpawner/dev/run_swarmspawner.py
    main = JupyterHub.launch_instance

    print("Loading config: {}".format(JupyterHub.config_file))
    # Run the JupyterHub service
    main()
