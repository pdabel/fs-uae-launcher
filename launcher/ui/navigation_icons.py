import qtawesome as qta

import fsui
from fsui.qt import (
    QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPen, QPixmap,
    QRect, Qt,
)


class RetroNavigationIcon(QIconEngine):
    def __init__(self, name, variant):
        super().__init__()
        self.name = name
        self.variant = variant
        self.glyph = qta.icon(
            name, color="#0055aa" if variant == "workbench" else "#183867"
        )

    def clone(self):
        return RetroNavigationIcon(self.name, self.variant)

    def paint(self, painter, rect, mode, state):
        painter.save()
        extent = min(rect.width(), rect.height())
        painter.translate(
            rect.x() + (rect.width() - extent) / 2,
            rect.y() + (rect.height() - extent) / 2,
        )
        painter.scale(extent / 24, extent / 24)
        painter.setRenderHint(QPainter.Antialiasing)
        if mode == QIcon.Disabled:
            painter.setOpacity(0.4)
        if self.variant == "workbench":
            outline = QPainterPath()
            outline.moveTo(3, 2)
            outline.lineTo(17, 2)
            outline.lineTo(21, 6)
            outline.lineTo(21, 22)
            outline.lineTo(3, 22)
            outline.closeSubpath()
            painter.setPen(QPen(QColor("#102e60"), 1.2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawPath(outline)
            painter.fillRect(QRect(4, 18, 16, 3), QColor("#ff8800"))
            painter.setPen(QPen(QColor("#0055aa"), 1.2))
            painter.drawLine(17, 2, 17, 6)
            painter.drawLine(17, 6, 21, 6)
            glyph_rect = QRect(5, 5, 13, 12)
        else:
            painter.fillRect(QRect(4, 4, 19, 19), QColor("#546a85"))
            painter.setPen(QPen(QColor("#183867"), 1.2))
            painter.setBrush(QColor("#f4f8ff"))
            painter.drawRect(QRect(2, 1, 19, 20))
            painter.fillRect(QRect(3, 2, 17, 4), QColor("#168c9e"))
            painter.fillRect(QRect(17, 3, 2, 2), QColor("#ffd36b"))
            painter.setPen(QPen(QColor("#d7e7f5"), 1))
            painter.drawLine(3, 20, 20, 20)
            glyph_rect = QRect(5, 7, 13, 12)
        self.glyph.paint(painter, glyph_rect, Qt.AlignCenter, QIcon.Normal)
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        finally:
            painter.end()
        return pixmap


def navigation_icon(name):
    if fsui.theme_variant in ("windows311", "workbench"):
        return QIcon(RetroNavigationIcon(name, fsui.theme_variant))
    return qta.icon(name, color="#9bcce2")