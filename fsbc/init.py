import fsbc.debug
import fsbc.i18n
import fsbc.logging

from fsbc.application import Application


def initialize_application(
    name=None,
    version=None,
    logs_dir=None,
    gettext=None,
    enable_logging=True,
    enable_exception_handler=True,
):
    if name and logs_dir and enable_logging:
        fsbc.logging.setup_logging(name + ".log.txt", logs_dir)

    if gettext is not None:
        fsbc.i18n.set_gettext(gettext)

    if name is not None:
        Application.app_name = name

    if version is not None:
        Application.app_version = version

    if enable_exception_handler:
        fsbc.debug.enable_exception_handler()
