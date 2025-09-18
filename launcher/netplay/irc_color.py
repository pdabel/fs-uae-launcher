from fsui.qt import QPalette

class IRCColor:
    JOIN = (64, 164, 64)
    POS_MODE = (64, 164, 64)

    PART = (164, 64, 64)
    NEG_MODE = (164, 64, 64)

    KICK = (255, 64, 64)
    WARNING = (255, 0, 0)

    INFO = (64, 128, 255)

    pt = QPalette().color(QPalette.ColorRole.Text)
    MESSAGE = (pt.red, pt.green, pt.blue)
    MY_MESSAGE = (164, 164, 164)

    TOPIC = (192, 128, 0)

    NOTICE = (164, 64, 164)
