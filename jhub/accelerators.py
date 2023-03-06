from http.cookiejar import LoadError
import os
import random
from jhub.defaults import default_base_path
from jhub.io import acquire_lock, load, release_lock, write, exists


class AcceleratorPool:
    """
    Accelerator pool used to fetch the next available
    accelerator for the requesting user.
    """

    _lock_path = os.path.join(default_base_path, "accelerator_pool_lock")
    _type = None
    _oversubscribe = False
    # List or file path
    _mappings = None

    _free_pool = None
    _claimed_pool = None

    def __init__(
        self, type="generic", oversubscribe=False, mappings=None, mappings_file_path=None
    ):
        """Load in the type of accelerator and the associated mappings that are available"""
        self._type = type
        self._oversubscribe = oversubscribe
        if not mappings:
            self._mappings = {}
        else:
            self._mappings = mappings

        # Ensure that the lockfile is present
        if not exists(self._lock_path):
            created = write(self._lock_path, "", mkdirs=True)
            if not created:
                raise IOError("Failed to create the required lock file for the Accelerator Pool: {}".format(
                    created
                ))

        if mappings_file_path:
            loaded_mappings = load(mappings_file_path)
            if not loaded_mappings:
                raise LoadError("Failed to load Accelerator Pool mappings")
            self._mappings = loaded_mappings

        if not self._free_pool:
            self._free_pool = {}
        if not self._claimed_pool:
            self._claimed_pool = {}

        if self._mappings:
            for _id, value in self._mappings.items():
                self._free_pool[_id] = value

    def aquire(self, user, logger=None):
        """A user requests to aquire an accelerator"""
        # We assume that the _mappings is a dictionary
        # TODO, add mutex
        lock = acquire_lock(self._lock_path)
        if not self._free_pool:
            if logger:
                logger.debug("Free pool is empty {}".format(self._free_pool))
            return None

        # Selected a random accelerator
        free_list = list(self._free_pool.keys())
        random_accelerator = random.choice(free_list)
        selected_accelerator = self._free_pool.pop(random_accelerator)
        self._claimed_pool[selected_accelerator] = {"user": user}

        release_lock(lock)
        if logger:
            logger.debug("Selected accelerator: {}".format(selected_accelerator))
        return selected_accelerator

    def release(self, user, logger=None):
        """A user releases an accelerator"""
        lock = acquire_lock(self._lock_path)

        user_accelerators = []
        for accelerator, data in self._claimed_pool.items():
            if user in data:
                user_accelerators.append(accelerator)

        if logger:
            logger.debug("Releasing user accelerator: {}".format(user_accelerators))

        for accelerator in user_accelerators:
            self._claimed_pool.pop(accelerator)
            self._free_pool[accelerator] = True

        release_lock(lock)
        return True

    def get_pool_type(self):
        return self._type


class AcceleratorManager:

    _db = None

    def __init__(self, db):
        if not isinstance(db, dict):
            raise TypeError("The AcceleratorManager requires the db to a dictionary")
        self._db = db

    def get_pool(self, pool_id):
        if pool_id not in self._db:
            return None
        return self._db[pool_id]

    def get_pool_type(self, pool_id):
        if pool_id not in self._db:
            return None
        return self._db[pool_id].get_pool_type()

    def add_pool(self, pool_id, pool):
        self._db[pool_id] = pool

    def remove_pool(self, pool):
        self._db.pop(pool)

    def request(self, pool_id, owner, logger=None):
        pool = self.get_pool(pool_id)
        if not pool:
            return None
        return pool.aquire(owner, logger=logger)

    def release(self, pool_id, owner, logger=None):
        pool = self.get_pool(pool_id)
        if not pool:
            return None
        return pool.release(owner, logger=logger)
        


