import os
from functools import lru_cache
from uuid import uuid4
from zipfile import ZipFile

import requests

from fsgs.FSGSDirectories import FSGSDirectories
from fsgs.network import openretro_url_prefix


@lru_cache()
def get_cache_zip_for_sha1(sha1):
    zip_path = os.path.join(FSGSDirectories.images_dir(), sha1[:2] + ".zip")
    try:
        return ZipFile(zip_path, "r")
    except Exception:
        return None


def get_file_for_sha1_cached(sha1, size_arg, cache_ext):
    cache_zip = get_cache_zip_for_sha1(sha1)
    if cache_zip is not None:
        try:
            return cache_zip.open("{}/{}{}".format(sha1[:2], sha1, cache_ext))
        except KeyError:
            pass
    cache_dir = FSGSDirectories.images_dir_for_sha1(sha1)
    cache_file = os.path.join(cache_dir, sha1 + cache_ext)
    if os.path.exists(cache_file):
        # An old bug made it possible for 0-byte files to exist, so
        # we check for that here...
        if os.path.getsize(cache_file) > 0:
            return cache_file

    url = "{}/image/{}{}".format(openretro_url_prefix(), sha1, size_arg)
    print("[IMAGES]", url)

    r = requests.get(url, stream=True)
    try:
        r.raise_for_status()
        cache_file_partial = "{}.{}.partial".format(
            cache_file, str(uuid4())[:8]
        )
        if not os.path.exists(os.path.dirname(cache_file_partial)):
            os.makedirs(os.path.dirname(cache_file_partial))
        with open(cache_file_partial, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    finally:
        r.close()
    os.rename(cache_file_partial, cache_file)
    return cache_file
