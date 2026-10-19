"""Apply a netplay config document to the local launcher config.

The host's config arrives as sync keys. Most are set as they are, but
kickstarts and media are sent by SHA-1 and have to be found in the local
file database first. Whatever can't be found is returned, not reported:
the caller decides whether that is a message in a channel or the
"missing" list of a ready call.

A lobby document comes with its own key lists, and is applied and hashed
against those rather than this launcher's: launchers whose Sync Config
limits differ build different lists, and would otherwise drop each
other's media slots and never agree on the hash. The lists come from
the host, though, so they only narrow what this launcher would sync
anyway (accepted_keys). See "Key lists travel with the document" in
docs/netplay-go-server-design.md.

resolve_config is pure and takes its dependencies as arguments, so it
can be tested without the launcher; apply_config and apply_document wire
it to the live config.
"""

import re

from fsgs.amiga.amiga import Amiga

# SHA-1 key -> the path keys it resolves to.
KICKSTART_KEYS = {
    "x_kickstart_file_sha1": ("kickstart_file", "x_kickstart_file"),
    "x_kickstart_ext_file_sha1": (
        "kickstart_ext_file",
        "x_kickstart_ext_file",
    ),
}

# x_floppy_drive_3_sha1 -> floppy_drive_3, and the same for every media
# kind. Matched by name rather than listed up to this launcher's limits,
# so a slot beyond them is still resolved to a path.
MEDIA_SHA1_KEY = re.compile(
    r"^x_((?:floppy_drive|floppy_image|cdrom_drive|cdrom_image|hard_drive)"
    r"_\d+)_sha1$"
)


def media_path_key(key):
    """The path key a media SHA-1 key resolves to, or None."""
    m = MEDIA_SHA1_KEY.match(key)
    return m.group(1) if m else None


def accepted_keys(document_keys, local_sync_keys):
    """The document's sync keys this launcher will apply.

    The document's lists are the host's, so they narrow what is applied
    but can't widen it: a key is taken only if this launcher syncs it
    too, or it is a media SHA-1 key, matched by name so a host's extra
    slots still resolve. Anything else -- a key a newer launcher added,
    or a local-only one such as a raw hard_drive_0 path -- keeps its
    local value, and if it is hashed, the slot shows a mismatch.
    """
    return {
        key
        for key in document_keys
        if key in local_sync_keys or media_path_key(key) is not None
    }


def resolve_config(document, sync_keys, find_by_sha1):
    """Work out the config changes a document makes locally.

    Returns (updates, missing): updates is a list of (key, value) pairs
    to set, and missing maps each SHA-1 key that could not be resolved to
    the SHA-1 it was sent with. Keys outside sync_keys are ignored.
    """
    updates = []
    missing = {}
    for key, value in document.items():
        if key not in sync_keys:
            continue
        path_key = media_path_key(key)
        if key in KICKSTART_KEYS:
            path_keys = KICKSTART_KEYS[key]
            if key == "x_kickstart_file_sha1" and (
                value == Amiga.INTERNAL_ROM_SHA1
            ):
                path = "internal"
            elif not value:
                # No kickstart, not a missing one: the host has none set,
                # which the launch treats as the internal ROM, so clearing
                # it here gives every player the same.
                path = ""
            else:
                path = find_by_sha1(value)
                if not path:
                    # Leave the current kickstart in place.
                    missing[key] = value
                    continue
            updates.extend((path_key, path) for path_key in path_keys)
            updates.append((key, value))
        elif path_key is not None:
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


def apply_config(document, sync_keys=None):
    """Apply a document to LauncherConfig and return what's missing.

    sync_keys defaults to this launcher's own, which is right only for
    config that didn't come with a key list (the IRC path).
    """
    from fsgs.context import fsgs
    from launcher.launcher_config import LauncherConfig

    updates, missing = resolve_config(
        document,
        LauncherConfig.sync_keys_set if sync_keys is None else sync_keys,
        lambda sha1: fsgs.file.find_by_sha1(sha1=sha1),
    )
    if updates:
        LauncherConfig.set_multiple(updates)
    return missing


def apply_document(snapshot):
    """Apply a lobby snapshot's config and hash the result.

    Returns (config_hash, missing), the body of the ready call for the
    snapshot's config_version: the hash is checksum_config over the
    document's own checksum list, taken from the live config after
    applying, so a file that couldn't be found shows up in both.
    """
    from fsgs.context import fsgs
    from launcher.launcher_config import LauncherConfig

    keys = snapshot["keys"]
    missing = apply_config(
        snapshot["config"],
        accepted_keys(keys["sync"], LauncherConfig.sync_keys_set),
    )
    config_hash = LauncherConfig.checksum_config(
        fsgs.config.copy(), keys["checksum"]
    )
    return config_hash, missing
