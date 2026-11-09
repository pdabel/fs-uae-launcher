from fsui.qt.helpers import QParent
from fsui.qt.qt import QEvent, QSpinBox, QStyle, QStyleOptionFrame
from fsui.qt.signal import Signal, SignalWrapper
from fsui.qt.widget import Widget


class _SpinBox(QSpinBox):
    def event(self, event):
        result = super().event(event)
        if event.type() in (
            QEvent.Resize,
            QEvent.Show,
            QEvent.StyleChange,
            QEvent.LayoutDirectionChange,
        ):
            # Qt 6.12 can place the editor outside the stylesheet padding.
            option = QStyleOptionFrame()
            option.initFrom(self)
            contents = self.style().subElementRect(
                QStyle.SE_LineEditContents, option, self
            )
            # QLineEdit adds two pixels before its text; dropdowns do not.
            contents.setLeft(max(0, contents.left() - 2))
            editor = self.lineEdit()
            editor.setGeometry(editor.geometry().intersected(contents))
        return result


class SpinCtrl(Widget):
    changed_signal = Signal()

    def __init__(self, parent, min_value, max_value, initial_value):
        super().__init__(parent)
        self.set_widget(_SpinBox(QParent(parent)))
        self._widget.setRange(min_value, max_value)
        self._widget.setValue(initial_value)
        self._widget.valueChanged.connect(self.__value_changed)
        self.changed = SignalWrapper(self, "changed")

    def get_value(self):
        return self._widget.value()

    def set_value(self, value):
        self._widget.setValue(value)

    def __value_changed(self, _):
        if not self.changed.inhibit:
            self.on_changed()

    def on_change(self):
        self.changed.emit()
