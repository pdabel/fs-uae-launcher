import os


def encode_path(path):
    return path


def unicode_path(path):
    return path


def normalize_path(path):
    path = os.path.normcase(os.path.normpath(path))
    return unicode_path(path)
