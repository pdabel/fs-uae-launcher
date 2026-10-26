import os
from importlib.resources import files

from .application import Application


class Resources(object):
    def __init__(self, package, subdir=""):
        self.package = package
        self.subdir = subdir
        self.resource_sha1s = {}

    def resource_name(self, resource):
        if self.subdir:
            return self.subdir + "/" + resource
        return resource

    def stream(self, resource):
        print("Resources.stream", resource)
        resource_name = self.resource_name(resource)
        try:
            return files(self.package).joinpath(resource_name).open("rb")
        except Exception as e:
            print(e)
        try:
            return open(self.path(resource), "rb")
        except FileNotFoundError:
            raise LookupError(resource)

    def path(self, resource):
        application = Application.get_instance()
        resource_name = self.resource_name(resource)
        print("looking up resource", resource_name)
        print("- package:", self.package)

        relative_path = os.path.join(self.package, resource_name)
        try:
            return application.data_file(relative_path)
        except LookupError:
            pass

        try:
            path = files(self.package).joinpath(resource_name)
            if path.is_file():
                return str(path)
        except Exception:
            pass

        raise LookupError(f"Cannot find resource {repr(resource)}")
