"""Apply a netplay config document to the local launcher config.

The host's config arrives as sync keys. Most are set as they are, but
kickstarts and media are sent by SHA-1 and have to be found in the local
file database first. Whatever can't be found is returned, not reported:
the caller decides whether that is a message in a channel or the
"missing" list of a ready call.

resolve_config is pure and takes its dependencies as arguments, so it
can be tested without the launcher; apply_config wires it to the live
config.
"""

from fsgs.amiga.amiga import Amiga

# SHA-1 key -> the path keys it resolves to.
KICKSTART_KEYS = {
    "x_kickstart_file_sha1": ("kickstart_file", "x_kickstart_file"),
    "x_kickstart_ext_file_sha1": (
        "kickstart_ext_file",
        "x_kickstart_ext_file",
    ),
}


def file_keys(limits):
    """Map each media SHA-1 key to its path key, up to the given limits.

    limits has the MAX_* attributes of launcher.sync_settings; it is read
    on every call because the Sync Config dialog changes it at runtime.
    """
    keys = {}
    for kind, count in [
        ("floppy_drive", limits.MAX_FLOPPY_DRIVES),
        ("floppy_image", limits.MAX_FLOPPY_IMAGES),
        ("cdrom_drive", limits.MAX_CDROM_DRIVES),
        ("cdrom_image", limits.MAX_CDROM_IMAGES),
        ("hard_drive", limits.MAX_HARD_DRIVES),
    ]:
        for i in range(count):
            keys[f"x_{kind}_{i}_sha1"] = f"{kind}_{i}"
    return keys


def resolve_config(document, limits, sync_keys, find_by_sha1):
    """Work out the config changes a document makes locally.

    Returns (updates, missing): updates is a list of (key, value) pairs
    to set, and missing maps each SHA-1 key that could not be resolved to
    the SHA-1 it was sent with. Keys outside sync_keys are ignored.
    """
    media_keys = file_keys(limits)
    updates = []
    missing = {}
    for key, value in document.items():
        if key not in sync_keys:
            continue
        if key in KICKSTART_KEYS:
            path_keys = KICKSTART_KEYS[key]
            if key == "x_kickstart_file_sha1" and (
                value == Amiga.INTERNAL_ROM_SHA1
            ):
                path = "internal"
            elif key == "x_kickstart_ext_file_sha1" and not value:
                path = ""
            else:
                path = find_by_sha1(value)
                if not path:
                    # Leave the current kickstart in place.
                    missing[key] = value
                    continue
            updates.extend((path_key, path) for path_key in path_keys)
            updates.append((key, value))
        elif key in media_keys:
            path_key = media_keys[key]
            if not value:
                path = ""
            elif value.startswith(("http://", "https://")):
                path = value
            else:
                path = find_by_sha1(value)
                if not path:
                    # Clear the slot rather than keep a different disk.
                    missing[key] = value
                    value = ""
            updates.extend([(path_key, path or ""), (key, value)])
        else:
            updates.append((key, value))
    return updates, missing


def apply_config(document):
    """Apply a document to LauncherConfig and return what's missing."""
    from fsgs.context import fsgs
    from launcher.launcher_config import LauncherConfig
    from launcher.sync_settings import sync_settings

    updates, missing = resolve_config(
        document,
        sync_settings,
        LauncherConfig.sync_keys_set,
        lambda sha1: fsgs.file.find_by_sha1(sha1=sha1),
    )
    if updates:
        LauncherConfig.set_multiple(updates)
    return missing
