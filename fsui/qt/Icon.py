from fsui.qt import QPixmap, QImage, QIcon
from fsbc.resources import Resources
from .Image import Image


class Icon(object):
    def __init__(self, name, path):
        self.name = name
        self.path = path

    def data_for_size(self, size):
        assert self.path.startswith("pkg:")
        resources = Resources(self.path[4:])
        try:
            return resources.read(f"res/{size}x{size}/{self.name}.png")
        except LookupError:
            return resources.read(f"res/{size}/{self.name}.png")

    def qimage(self, size):
        qimage = QImage()
        qimage.loadFromData(self.data_for_size(size))
        return qimage

    def image(self, size):
        return Image(object=self.qimage(size))

    def qpixmap(self, size):
        return QPixmap(self.qimage(size))

    def qicon(self, size=None):
        icon = QIcon()
        if size is not None:
            sizes = [size]
        else:
            sizes = [16, 22, 24, 32, 40, 48, 64, 128, 256]
        for size in sizes:
            try:
                pixmap = self.qpixmap(size)
            except Exception:
                pass
            else:
                icon.addPixmap(pixmap)
        return icon
