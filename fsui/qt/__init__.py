import traceback
import queue

from fsui.res import gettext
from fsui.qt.qt import (
    init_qt,
    QEvent,
    QObject,
    QCoreApplication,
    QTimer,
    QMessageBox,
    QCursor,
)
from fsui.qt.qt import *
from fsui.qt.helpers import QParent


def get_screen_size():
    application = init_qt()
    geometry = application.primaryScreen().virtualGeometry()
    size = geometry.width(), geometry.height()
    print("using screen size", size)
    return size


def get_mouse_position():
    # noinspection PyArgumentList
    pos = QCursor.pos()
    return pos.x(), pos.y()


class CustomEvent(QEvent):
    def __init__(self):
        QEvent.__init__(self, QEvent.User)


class EventHandler(QObject):
    def __init__(self):
        QObject.__init__(self)
        self.queue = queue.Queue()

    def customEvent(self, event):
        while True:
            try:
                function, args, kwargs = self.queue.get_nowait()
            except queue.Empty:
                break
            try:
                function(*args, **kwargs)
            except Exception:
                print("-- callback exception --")
                traceback.print_exc()

    def post_callback(self, function, *args, **kwargs):
        self.queue.put((function, args, kwargs))
        QCoreApplication.instance().postEvent(self, CustomEvent())


event_handler = EventHandler()


def call_after(function, *args, **kwargs):
    event_handler.post_callback(function, *args, **kwargs)


def call_later(duration, function, *args, **kwargs):
    # QApplication.instance().
    def timer_callback():
        function(*args, **kwargs)

    QTimer.singleShot(duration, timer_callback)


def show_error(message, title=None, parent=None):
    if not title:
        title = gettext("An Error Occurred")
    QMessageBox.critical(QParent(parent), title, message)


def show_warning(message, title=None, parent=None):
    if not title:
        title = gettext("Warning")
    QMessageBox.warning(QParent(parent), title, message)
