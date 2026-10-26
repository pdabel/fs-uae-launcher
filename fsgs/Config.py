import sys

from collections import defaultdict

from fsbc import settings
from fsgs.option import Option
from .contextaware import ContextAware


class Config(ContextAware):
    def __init__(self, context):
        ContextAware.__init__(self, context)
        self.values = {}
        self.log_config = settings.get(Option.LAUNCHER_LOG_CONFIG) == "1"

    def add_behavior(self, instance, options):
        # FIXME: Move to fsgs
        from launcher.ui.behaviors.configbehavior import ConfigBehavior

        ConfigBehavior(instance, options)

    def copy(self):
        # Return a defaultdict so lookups for unset keys returns empty strings.
        return defaultdict(str, self.values)

    def get(self, key, default=""):
        return self.values.get(key, default)

    def items(self):
        return self.values.items()

    def clear(self):
        for key in list(self.values.keys()):
            value = self.values[key]
            if value:
                self.set(key, "")

    @staticmethod
    def config_from_argv():
        config = []
        for arg in sys.argv:
            if arg.startswith("--config:"):
                arg = arg[9:]
                key, value = arg.split("=", 1)
                key = key.replace("-", "_")
                config.append((key, value))
        return config

    def add_from_argv(self):
        """Adds config parameters from argv to currently loaded configuration.
        :return: True if config parameters were used.
        """
        config_items = self.config_from_argv()
        for key, value in config_items:
            self.set(key, value)
        return len(config_items) > 0

    def load(self, values):
        self.clear()
        for key, value in list(values.items()):
            self.set(key, value)

    def load_from_file(self):
        pass

    def set(self, *values):
        if len(values) == 1:
            items = list(values[0])
        elif len(values) == 2:
            items = [(values[0], values[1])]
        else:
            raise Exception("Invalid number of parameters to set_config")

        item_keys = [x[0] for x in items]
        changed_keys = set()

        def add_changed_key(added_key):
            added_priority = 0
            # FIXME: re-introduce support for key priority if necessary
            changed_keys.add((added_priority, added_key))

        def change(changed_key, changed_value):
            if old_config.get(changed_key, None) == changed_value:
                return
            if self.log_config:
                print(
                    f"[CONFIG] set {changed_key} to {changed_value}"
                )
            add_changed_key(changed_key)
            self.values[changed_key] = changed_value

        old_config = self.values.copy()
        for key, value in items:
            change(key, value)
            # we now reset x_key_sha1 keys, so if a file option was set without
            # simultaneously specifying the _sha1 key, that key will be reset.
            reset_key = "x_" + key + "_sha1"
            if reset_key not in item_keys:
                if reset_key in self.values:
                    change(reset_key, "")

        # and now broadcast all changed keys at once
        changed_key_list = [x[1] for x in changed_keys]

        if len(changed_keys) > 0:
            if "__ready" not in changed_key_list:
                change("__ready", "0")
            for key in changed_key_list:
                if not key.startswith("__implicit_"):
                    change("__changed", "1")
                    break
            for priority, key in sorted(changed_keys):
                value = self.get(key)
                self.context.signal.notify("config", (key, value))
