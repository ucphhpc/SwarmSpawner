import os
import fcntl


def makedirs(path):
    try:
        os.makedirs(path)
        return True
    except Exception as err:
        print("Failed to create directory path: {} - {}".format(path, err))
    return False


def acquire_lock(path, mode=fcntl.LOCK_EX):
    lock = open(path, "w+")
    try:
        fcntl.flock(lock.fileno(), mode)
    except IOError as ioerr:
        print("Failed to acquire lock: {} - {}".format(path, ioerr))
        # Clean up
        try:
            lock.close()
        except Exception as err:
            print("Failed to close lock after failling to acquire it: {}".format(err))
    return lock


def release_lock(lock, close=True):
    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    if close:
        try:
            lock.close()
        except Exception as err:
            print("Failed to close file during lock release: {} - {}".format(lock, err))


def write(path, content, mode="w", mkdirs=False):
    dir_path = os.path.dirname(path)
    if not os.path.exists(dir_path) and mkdirs:
        if not makedirs(dir_path):
            return False
    try:
        with open(path, mode) as fh:
            fh.write(content)
        return True
    except Exception as err:
        print("Failed to save file: {} - {}".format(path, err))
    return False


def load(path, mode="r", readlines=False):
    try:
        with open(path, mode) as fh:
            if readlines:
                return fh.readlines()
            return fh.read()
    except Exception as err:
        print("Failed to load file: {} - {}".format(path, err))
    return False


def remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception as err:
        print("Failed to remove file: {} - {}".format(path, err))
    return False


def remove_content_from_file(path, content):

    if not os.path.exists(path):
        return False

    if not content:
        return False

    lines = []
    with open(path, "r") as rh:
        lines = rh.readlines()

    with open(path, "w") as wh:
        for current_line in lines:
            if content not in current_line:
                wh.write(current_line)


def exists(path):
    return os.path.exists(path)


def chmod(path, mode, **kwargs):
    try:
        os.chmod(path, mode, **kwargs)
    except Exception as err:
        print("Failed to set permissions: {} on: {} - {}".format(mode, path, err))
        return False
    return True
