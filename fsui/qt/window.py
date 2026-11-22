import traceback
import weakref

from fsbc.system import macosx

from fsui.qt import QMainWindow, QObject, QSignal, QWidget, Qt
from fsui.qt.qt import init_qt, QEvent

# noinspection PyProtectedMember
from fsui.qt.helpers import QParent

windows: set = set()


# noinspection PyProtectedMember
class RealWindow(QMainWindow):
    def __init__(
        self,
        parent,
        child,
        minimizable=True,
        maximizable=True,
        border=True,
        below=False,
    ):
        super().__init__(parent)

        flags = Qt.WindowType.Window
        if macosx:
            flags &= ~Qt.WindowType.WindowFullscreenButtonHint

        if border:
            flags |= Qt.WindowType.CustomizeWindowHint
            flags |= Qt.WindowType.WindowCloseButtonHint
            flags |= Qt.WindowType.WindowTitleHint
            if minimizable:
                flags |= Qt.WindowType.WindowMinimizeButtonHint
            if maximizable:
                flags |= Qt.WindowType.WindowMaximizeButtonHint
        else:
            flags |= Qt.WindowType.FramelessWindowHint
            flags |= Qt.WindowType.NoDropShadowWindowHint
            if below:
                flags |= Qt.WindowType.WindowStaysOnBottomHint
        self.setWindowFlags(flags)

        self._child = child
        self.__already_closed = False
        self._size_set = False

    @property
    def child(self):
        return self._child

    def resize_to(self, size):
        print("RealWindow.resize_to", size[0], size[1])
        assert isinstance(self.child._real_widget, QWidget)
        self.child._real_widget.setGeometry(0, 0, size[0], size[1])

    def set_size(self, size):
        self._size_set = True
        print("RealWindow.set_size", size)
        self.resize(size[0], size[1])

    def position(self):
        return self.pos().x(), self.pos().y()

    def set_position(self, position):
        self.move(position[0], position[1])

    def closeEvent(self, event):
        print(str(self) + ".closeEvent")
        event.accept()
        self.__on_closed()

    def showEvent(self, event):
        event.accept()
        self.child.shown.emit()

    def resizeEvent(self, event):
        size = event.size()
        print("RealWindow.resizeEvent", size.width(), size.height())
        print(size, "vs", self.size())
        # According to docs, event.size() should be same as
        # QWidget.size(), but this isn't always the case :-/.
        size = self.size()
        self.resize_to((size.width(), size.height()))

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self.child.on_resize()
        QMainWindow.changeEvent(self, event)

    def __on_closed(self):
        try:
            print("RealWindow.__on_closed")
            if self.__already_closed:
                print("Looks like a duplicate event, ignoring this one")
                return
            print("closed.emit")
            self.child.closed.emit()
            self.child.on_close()
            self.__already_closed = True
        except Exception:
            traceback.print_exc()

    def is_maximized(self):
        return self.windowState() == Qt.WindowState.WindowMaximized

    def is_fullscreen(self):
        return self.windowState() == Qt.WindowState.WindowFullScreen

    def set_maximized(self, maximize=True, geometry=None):
        print("set_maximized", maximize)
        if maximize:
            self.showMaximized()
            print(
                "size after showMaximized",
                (self.size().width(), self.size().height()),
            )
        else:
            self.setWindowState(Qt.WindowState.WindowNoState)

    def set_fullscreen(self, fullscreen=True, geometry=None):
        print("set_fullscreen", fullscreen)
        if fullscreen:
            # Workaround, without setting size to something initially,
            # showFullScreen sometimes fails to update size on Linux, causing
            # only a small part of the screen to be filled.
            if geometry is not None:
                print("set_fullscreen geometry", geometry)
                self.setGeometry(*geometry)
            else:
                if not self._size_set:
                    self._size_set = True
                    print("resizing to 1, 1")
                    self.resize(1, 1)
            self.showFullScreen()
            print(
                "size after showFullScreen",
                (self.size().width(), self.size().height()),
            )
        else:
            self.setWindowState(Qt.WindowState.WindowNoState)

    def minimize(self):
        self.setWindowState(Qt.WindowState.WindowMinimized)


# noinspection PyProtectedMember
class RealWidget(QWidget):
    def __init__(self, parent, owner):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self._owner = weakref.ref(owner)
        self._centered_on_initial_show = False

    def owner(self):
        return self._owner()

    def resizeEvent(self, event):
        self.owner().on_resize()

    def showEvent(self, _):
        if self.owner().center_on_show:
            if not self._centered_on_initial_show:
                if self.parent():
                    self.owner().center_on_parent()
                self._centered_on_initial_show = True

        self.owner().set_initial_size_from_layout()
        self.owner().on_resize()


# noinspection PyPep8Naming
class Window(QObject):

    shown = QSignal()
    closed = QSignal()

    def __init__(
        self,
        parent,
        title="",
        border=True,
        minimizable=True,
        maximizable=True,
        below=False,
        **_
    ):
        init_qt()
        super().__init__()

        # FIXME
        self._window = weakref.ref(self)

        self._real_window = RealWindow(
            QParent(parent, True),
            self,
            minimizable=minimizable,
            maximizable=maximizable,
            below=below,
            border=border,
        )

        self._real_widget = RealWidget(self._real_window, self)

        self.set_title(title)

        self.layout = None
        self._size_specified = False
        self.close_listeners = []
        self.destroyed.connect(self.__destroyed)

        self._real_window.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose, True
        )

        self.center_on_show = True
        self._centered_on_initial_show = False
        if hasattr(self, "accepted"):
            self.accepted.connect(self.__accepted)
        if hasattr(self, "rejected"):
            self.rejected.connect(self.__rejected)

        # Add a keep-alive reference
        print("Adding window reference", self)
        windows.add(self)
        self.closed.connect(self.__closed)

    def __closed(self):
        print("Removing window reference", self)
        windows.remove(self)

    @property
    def window(self):
        return self

    @property
    def visible(self):
        return self._real_window.isVisible()

    @visible.setter
    def visible(self, visible):
        self._real_window.setVisible(visible)

    def alert(self, msecs=0):
        init_qt().alert(self._real_window, msecs)

    def close(self):
        self._real_window.close()

    def real_window(self):
        return self._real_window

    def real_widget(self):
        return self._real_widget

    # DEPRECATED
    def get_container(self):
        return self.real_widget()

    # FIXME: Is this used?
    def center_on_initial_show(self):
        if self._centered_on_initial_show:
            return
        if self.layout and not self._size_specified:
            self.set_size(self.layout.get_min_size())
        self.on_resize()
        self.center_on_parent()
        self._centered_on_initial_show = True

    def __destroyed(self):
        print(str(self) + ".__destroyed")

    def add_close_listener(self, function):
        self.closed.connect(function)

    def top_level(self):
        return self

    def set_icon(self, icon):
        self.real_window().setWindowIcon(icon.qicon())

    def position(self):
        return self._real_window.position()

    def set_position(self, position):
        self._real_window.set_position(position)

    def size(self):
        return self.width(), self.height()

    def width(self):
        return self._real_window.width()

    def height(self):
        return self._real_window.height()

    def set_size(self, size):
        self._size_specified = True
        if size[0] == 0 or size[1] == 0:
            print("Window.set_size ignoring size", size)
            return
        print("Window.set_size", size)
        self._real_window.set_size(size)
        self._real_widget.resize(size[0], size[1])

    def set_initial_size_from_layout(self):
        if self.layout and not self._size_specified:
            self.set_size_from_layout()

    def set_size_from_layout(self):
        size = self.layout.get_min_size()
        print("set_size_from_layout, size =", size)
        self.set_size(size)

    def title(self):
        return self._real_window.windowTitle()

    def set_title(self, title):
        self._real_window.setWindowTitle(title)

    def show(self, maximized=False, center=False, offset=False):
        if center:
            print("CENTER")
            self.center_on_parent()
        elif offset:
            self.offset_from_parent((20, 20))
            self.center_on_show = False
        if maximized:
            self._real_window.showMaximized()
        else:
            self._real_window.show()

    def is_maximized(self):
        return self._real_window.is_maximized()

    def is_fullscreen(self):
        return self._real_window.is_fullscreen()

    def set_fullscreen(self, fullscreen=True, geometry=None):
        # We must set the size before maximizing, so this isn't done within
        # showMaximized -> ... -> set_initial_size_from_layout -> set_size.
        self.set_initial_size_from_layout()
        self._real_window.set_fullscreen(fullscreen, geometry)

    def set_maximized(self, maximize=True, geometry=None):
        # We must set the size before maximizing, so this isn't done within
        # showMaximized -> ... -> set_initial_size_from_layout -> set_size.
        self.set_initial_size_from_layout()
        self._real_window.set_maximized(maximize, geometry)

    def minimize(self):
        return self._real_window.minimize()

    def get_window_center(self):
        position = self.position()
        size = self.size()
        return position[0] + size[0] // 2, position[1] + size[1] // 2

    def center_on_parent(self):
        self.set_initial_size_from_layout()
        real_parent = self.real_window().parent()
        if real_parent:
            pp = real_parent.x(), real_parent.y()
            ps = real_parent.width(), real_parent.height()
            ss = self.size()
            print(pp, ps, ss)
            self.set_position(
                (pp[0] + (ps[0] - ss[0]) // 2, pp[1] + (ps[1] - ss[1]) // 2)
            )

    def offset_from_parent(self, offset):
        self.set_initial_size_from_layout()
        real_parent = self.real_window().parent()
        if real_parent:
            pp = real_parent.x(), real_parent.y()
            self.set_position((pp[0] + offset[0], pp[1] + offset[1]))

    def center_on_screen(self):
        frame_rect = self._real_window.frameGeometry()
        frame_rect.moveCenter(
            self._real_window.screen().availableGeometry().center()
        )
        self._real_window.move(frame_rect.topLeft())

    def set_background_color(self, color):
        p = self.real_widget().palette()
        p.setColor(self.real_widget().backgroundRole(), color)
        self.real_widget().setPalette(p)

    def is_shown(self):
        return self._real_window.isVisible()

    def raise_and_activate(self):
        self._real_window.raise_()
        self._real_window.activateWindow()

    def on_close(self):
        pass

    def __rejected(self):
        print(str(self) + ".__rejected")
        self.__on_closed()

    def __accepted(self):
        print(str(self) + ".__accepted")
        self.__on_closed()

    def on_resize(self):
        if self.layout:
            self.layout.set_size(self.get_size())
            self.layout.update()

    # DEPRECATED
    def resize(self, width, height):
        self.set_size((width, height))

    # DEPRECATED
    def get_size(self):
        return self.size()

    def get_window(self):
        return self.top_level()

    # DEPRECATED
    def get_position(self):
        return self.position()

    # DEPRECATED
    def maximized(self):
        return self.is_maximized()

    # DEPRECATED
    def get_parent(self):
        return None

    # DEPRECATED
    def set_icon_from_path(self, _):
        print("FIXME: Window.set_icon_from_path")

    # DEPRECATED
    def get_title(self):
        return self.title()

    # DEPRECATED
    def maximize(self, maximize=True):
        return self.set_maximized(maximize)
