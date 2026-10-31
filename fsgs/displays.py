import json
import logging


def display_id(screen):
    return "display:" + json.dumps(
        [
            screen.name(),
            screen.manufacturer(),
            screen.model(),
            screen.serialNumber(),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def matching_display_index(screens, monitor):
    for index, screen in enumerate(screens):
        if display_id(screen) == monitor:
            return index
    try:
        identity = json.loads(monitor[len("display:") :])
    except (ValueError, TypeError):
        logging.warning("Invalid saved display identity: %r", monitor)
        return None
    if not isinstance(identity, list) or len(identity) != 4:
        logging.warning("Invalid saved display identity: %r", monitor)
        return None
    _, manufacturer, model, serial = identity
    if serial:
        matches = [
            index
            for index, screen in enumerate(screens)
            if (screen.manufacturer(), screen.model(), screen.serialNumber())
            == (manufacturer, model, serial)
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def screen_index(screens, monitor, primary=None):
    if not screens:
        return None
    primary_index = next(
        (index for index, screen in enumerate(screens) if screen is primary), 0
    )
    if monitor and monitor.startswith("display:"):
        selected = matching_display_index(screens, monitor)
        return primary_index if selected is None else selected
    positions = {"left": 0, "middle-left": 1, "middle-right": 2, "right": 3}
    if monitor in positions:
        ordered = sorted(
            range(len(screens)),
            key=lambda index: (
                screens[index].geometry().x(),
                screens[index].geometry().y(),
                index,
            ),
        )
        return ordered[round(positions[monitor] / 3 * (len(screens) - 1))]
    return primary_index


def display_label(screen):
    geometry = screen.geometry()
    name = screen.name() or "Display"
    model = screen.model()
    if model and model != name:
        name += " - " + model
    return f"{name} ({geometry.width()}x{geometry.height()}, {geometry.x()},{geometry.y()})"


def fsuae_monitor(screens, monitor, primary=None):
    selected = screen_index(screens, monitor, primary)
    if selected is None:
        return None
    horizontal = screens[selected].geometry().x()
    if sum(screen.geometry().x() == horizontal for screen in screens) != 1:
        return None
    ordered = sorted(
        range(len(screens)), key=lambda index: screens[index].geometry().x()
    )
    rank = ordered.index(selected)
    if rank == 0:
        return "left"
    if rank == len(screens) - 1:
        return "right"
    for position, name in enumerate(
        ("left", "middle-left", "middle-right", "right")
    ):
        if round(position / 3 * (len(screens) - 1)) == rank:
            return name
    return None
