import weakref
from fsui.qt import QDialog, Signal
from fsui.qt.helpers import QParent


class LegacyDialog(QDialog):

    closed = Signal()

    def __init__(self, parent=None, title=""):
        QDialog.__init__(self, QParent(parent))
        self._window = weakref.ref(self)

        self.layout = None
        self.setWindowTitle(title)

        self.destroy_listeners = []
        self.close_listeners = []

    def get_parent(self):
        return None

    def closeEvent(self, event):
        print("Dialog.closeEvent")
        self.closed.emit()
        self.on_close()
        for function in self.close_listeners:
            print(function)
            function()
        event.accept()
        # remove close listeners so they will not keep the object alive
        self.close_listeners = []

    def add_close_listener(self, function):
        self.close_listeners.append(function)

    def get_window(self):
        return self

    def get_container(self):
        return self

    def show_modal(self):
        return self.exec()

    def end_modal(self, value):
        self.done(value)

    def center_on_parent(self):
        real_parent = self.parent()
        if real_parent:
            pp = real_parent.x(), real_parent.y()
            ps = real_parent.width(), real_parent.height()
            ss = self.get_size()
            self.move(
                pp[0] + (ps[0] - ss[0]) // 2, pp[1] + (ps[1] - ss[1]) // 2
            )

    def set_title(self, title):
        self.setWindowTitle(title)

    def set_size(self, size):
        self.resize(size[0], size[1])

    def on_create(self):
        pass

    def on_close(self):
        pass

    def on_destroy(self):
        pass

    def __destroy_event(self, event):
        self.on_destroy()

    def __close_event(self, event):
        print("__close_event")
        for function in self.close_listeners:
            function()
        self.on_close()
        self.Destroy()

    def showEvent(self, event):
        self.on_resize()

    def get_size(self):
        return self.width(), self.height()

    def resizeEvent(self, event):
        print("resized..")
        self.on_resize()

    def on_resize(self):
        if self.layout:
            self.layout.set_size(self.get_size())
            self.layout.update()

    def raise_and_activate(self):
        self.raise_()
        self.activateWindow()
