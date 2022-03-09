from http.cookiejar import LoadError
import os
import random
from jhub.defaults import default_base_path
from jhub.io import acquire_lock, load, release_lock


class AcceleratorPool:
    """
    Accelerator pool used to fetch the next available
    accelerator for the requesting user.
    """

    _lock_path = os.path.join(default_base_path, "accelerator_pool_lock")
    _type = None
    _oversubscribe = False
    # List or file path
    _ids = None

    _free_pool = None
    _claimed_pool = None

    def __init__(self, type, oversubscribe, ids=None, ids_file_path=None):
        self._type = type
        self._oversubscribe = oversubscribe
        if not ids:
            self._ids = []

        if ids_file_path:
            loaded_ids = load(ids_file_path)
            if not loaded_ids:
                raise LoadError("Failed to load accelerator ids")
            self._ids = loaded_ids

        if not self._free_pool:
            self._free_pool = {}
        if not self._claimed_pool:
            self._claimed_pool = {}

        if self._ids:
            for _id in self.ids:
                self._free_pool[_id] = True

    def aquire(self, user):
        """A user requests an accelerator"""
        # We assume that the _ids is a dictionary
        # TODO, add mutex
        lock = acquire_lock(self._lock_path)
        if not self._free_pool:
            return None

        # Selected a random accelerator
        free_list = list(self._free_pool)
        random_accelerator = random.choice(free_list)
        selected_accelerator = self._free_pool.pop(random_accelerator)
        self._claimed_pool[selected_accelerator] = {"user": user}

        release_lock(lock)
        return selected_accelerator

    def release(self, user):
        """A user releases an accelerator"""
        lock = acquire_lock(self._lock_path)

        user_accelerators = []
        for accelerator, data in self._claimed_pool.items():
            if user in data:
                user_accelerators.append(accelerator)

        for accelerator in user_accelerators:
            self._claimed_pool.pop(accelerator)
            self._free_pool[accelerator] = True

        release_lock(lock)
        return True
