import os


def running_in_gnome_3():
    value = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if value:
        return value == "GNOME"
    value = os.environ.get("DESKTOP_SESSION", "").upper()
    if value:
        return value == "GNOME"
    return False
