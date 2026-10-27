class StrWithExplicit(str):

    @property
    def int(self):
        return int(self or "0")


class ImplicitConfig:
    def __init__(self, config, settings):
        self._values = {}
        self._config = config
        self._settings = settings

    def items(self):
        return self._values.items()

    def get(self, key, default=""):
        value = self._values.get(key, default)
        explicit = self._config[key]
        if not explicit:
            explicit = self._settings[key]
        if value:
            result = StrWithExplicit(value)
        else:
            result = StrWithExplicit(explicit)
        result.explicit = explicit
        return result

    def __getitem__(self, item):
        result = self.get(item)
        return result

    def __setitem__(self, key, value):
        if not value:
            value = ""
        else:
            value = str(value)
        self._values[key] = value

    def __getattr__(self, item):
        result = self.get(item)
        return result

    def __setattr__(self, key, value):
        if key.startswith("_"):
            self.__dict__[key] = value
        else:
            self[key] = value


def normalize(value):
    n = ""
    for c in value.lower():
        if c in "abcdefghijklmnopqrstuvwxyz0123456789+":
            n += c
    return n
