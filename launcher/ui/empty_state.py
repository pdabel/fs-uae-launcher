"""Friendly placeholder shown inside an empty list view.

Centres a short message and an optional call-to-action button over the
view's viewport, and hides itself as soon as the view has rows.
"""

from fsui.qt import (
    QLabel, QListView, QModelIndex, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget, Qt,
)


class EmptyStateOverlay(QWidget):
    def __init__(self, view, title, hint="", action="", on_action=None):
        super().__init__(view.viewport())
        self.view = view
        self.setObjectName("emptyState")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)
        self.title = QLabel(title)
        self.title.setObjectName("emptyStateTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.hint = QLabel(hint)
        self.hint.setObjectName("emptyStateHint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setVisible(bool(hint))
        layout.addWidget(self.hint)
        self.button = QPushButton(action)
        self.button.setObjectName("emptyStateAction")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.button.setVisible(bool(action))
        if on_action is not None:
            self.button.clicked.connect(on_action)
        layout.addWidget(self.button, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        view.viewport().installEventFilter(self)
        model = self._model()
        if model is not None:
            for signal in (
                model.rowsInserted, model.rowsRemoved, model.modelReset,
                model.layoutChanged,
            ):
                signal.connect(self.refresh)
        self.refresh()

    def _model(self):
        # Some fsui views store their model in an attribute named `model`.
        return QListView.model(self.view)

    def eventFilter(self, watched, event):
        if watched is self.view.viewport() and event.type() == event.Type.Resize:
            self.setGeometry(self.view.viewport().rect())
        return False

    def set_text(self, title, hint=""):
        self.title.setText(title)
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))

    def refresh(self, *_):
        model = self._model()
        empty = model is None or model.rowCount(QModelIndex()) == 0
        self.setGeometry(self.view.viewport().rect())
        self.setVisible(empty)
        if empty:
            self.raise_()
