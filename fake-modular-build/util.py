import os


def make_absolute(path: str, wd: str) -> str:
    return os.path.normpath(os.path.join(wd, path))