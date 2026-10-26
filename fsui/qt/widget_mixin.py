import weakref
from fsui.qt import Qt, QPoint, QCursor
from fsui.qt import QFontMetrics, QPalette, QWidget
from ..common.layout import Layout
from .DrawingContext import Font
from .Color import Color


class MixinBase(object):
    def __init__(self):
        pass

    def init_mixin_base(self):
        pass


# noinspection PyPep8Naming
class WidgetMixin(MixinBase):
    def __init__(self, *_):
        self._parent = None
        self._window = None

    def init_widget(self, parent):
        self.init_mixin_base()
        self._parent = weakref.ref(parent)
        # noinspection PyProtectedMember
        self._window = parent._window

        widget = getattr(self, "_widget", self)
        assert isinstance(widget, QWidget)
        widget.installEventFilter(self.get_window())

        widget.destroyed.connect(self.on_destroy)

    def on_destroy(self):
        print("on_destroy")

    def eventFilter(self, obj, event):
        return False

    def get_parent(self):
        if self._parent is None:
            return None
        # noinspection PyCallingNonCallable
        return self._parent()

    def get_container(self):
        widget = getattr(self, "_widget", self)
        return widget

    def get_font(self):
        widget = getattr(self, "_widget", self)
        return Font(widget.font())

    def set_font(self, font):
        widget = getattr(self, "_widget", self)
        widget.setFont(font.font)

    def is_visible(self):
        widget = getattr(self, "_widget", self)
        return widget.isVisible()

    def visible(self):
        return self.is_visible()

    def measure_text(self, text):
        widget = getattr(self, "_widget", self)
        font = widget.font()
        metrics = QFontMetrics(font)
        return metrics.horizontalAdvance(text), metrics.height()

    def set_hand_cursor(self):
        widget = getattr(self, "_widget", self)
        widget.setCursor(Qt.PointingHandCursor)

    def set_normal_cursor(self):
        widget = getattr(self, "_widget", self)
        widget.setCursor(Qt.ArrowCursor)

    def is_enabled(self):
        widget = getattr(self, "_widget", self)
        return widget.isEnabled()

    def set_visible(self, visible):
        return self.show_or_hide(visible)

    def show_or_hide(self, show):
        widget = getattr(self, "_widget", self)
        if show:
            widget.show()
        else:
            widget.hide()

    def focus(self):
        widget = getattr(self, "_widget", self)
        widget.setFocus()

    def refresh(self):
        widget = getattr(self, "_widget", self)
        return widget.update()

    def set_min_width(self, width):
        # noinspection PyAttributeOutsideInit
        self.min_width = width

    def set_min_height(self, height):
        # noinspection PyAttributeOutsideInit
        self.min_height = height

    def get_min_width(self):
        widget = getattr(self, "_widget", self)
        width = 0
        if hasattr(self, "min_width"):
            if self.min_width:
                width = max(self.min_width, width)
        if hasattr(self, "layout") and isinstance(self.layout, Layout):
            width = max(self.layout.get_min_width(), width)
            return width
        result = max(width, widget.minimumSizeHint().width())
        return min(result, widget.maximumWidth())

    def get_min_height(self):
        widget = getattr(self, "_widget", self)
        assert isinstance(widget, QWidget)
        height = 0
        if hasattr(self, "min_height"):
            if self.min_height:
                height = max(self.min_height, height)
        if hasattr(self, "layout") and isinstance(self.layout, Layout):
            height = max(self.layout.get_min_height(), height)
            return height
        return max(height, widget.minimumSizeHint().height())

    def set_position(self, position, y=None):
        widget = getattr(self, "_widget", self)
        if y is None:
            widget.move(*position)
        else:
            widget.move(position, y)

    def set_size(self, size):
        widget = getattr(self, "_widget", self)
        widget.resize(*size)

    def set_position_and_size(self, position, size):
        widget = getattr(self, "_widget", self)
        widget.move(*position)
        widget.resize(*size)

    def get_window(self):
        # noinspection PyCallingNonCallable
        return self._window()

    def get_position(self):
        widget = getattr(self, "_widget", self)
        return widget.x(), widget.y()

    def get_size(self):
        widget = getattr(self, "_widget", self)
        return widget.width(), widget.height()

    def set_tool_tip(self, tool_tip):
        widget = getattr(self, "_widget", self)
        widget.setToolTip(tool_tip)

    def set_tooltip(self, tool_tip):
        self.set_tool_tip(tool_tip)

    def set_enabled(self, enable=True):
        widget = getattr(self, "_widget", self)
        widget.setEnabled(enable)

    # DEPRECATED
    def disable(self):
        return self.enable(False)

    # DEPRECATED
    def enable(self, enable=True):
        self.set_enabled(enable)

    def on_resize(self):
        if hasattr(self, "layout") and isinstance(self.layout, Layout):
            self.layout.set_size(self.get_size())
            self.layout.update()

    def get_background_color(self):
        # noinspection PyUnresolvedReferences
        return Color(self.palette().color(QPalette.Window))

    def set_background_color(self, color):
        # noinspection PyUnresolvedReferences
        self.setAutoFillBackground(True)
        widget = getattr(self, "_widget", self)
        p = widget.palette()
        # noinspection PyUnresolvedReferences
        p.setColor(self.backgroundRole(), color)
        widget.setPalette(p)

    def popup_menu(self, menu, pos=(0, 0), blocking=True):
        # popup does not block, and if menu goes out of the scope of the
        # caller, it will disappear (unless we keep a reference here
        # FIXME: using exec now
        widget = getattr(self, "_widget", self)
        global_pos = widget.mapToGlobal(QPoint(pos[0], pos[1]))
        menu.set_parent(self)
        if blocking:
            menu.qmenu.exec(global_pos)
        else:
            menu.qmenu.popup(global_pos)

        # Firing off a fake mouse left up event really assumes that the
        # menu was opened with a left down event, so implementation isn't
        # ideal. Better to add a listener to menu close instead.

    def is_mouse_over(self):
        # noinspection PyArgumentList
        c = QCursor.pos()
        # noinspection PyUnresolvedReferences
        p = self.mapToGlobal(QPoint(0, 0))
        s = self.get_size()
        if p.x() <= c.x() < p.x() + s[0] and p.y() <= c.y() < p.y() + s[1]:
            return True
        return False
