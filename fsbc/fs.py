import os

# noinspection PyUnresolvedReferences
from fsbc.user import get_data_dir


def encode_path(path):
    return path


def unicode_path(path):
    return path


def normalize_path(path):
    path = os.path.normcase(os.path.normpath(path))
    return unicode_path(path)
