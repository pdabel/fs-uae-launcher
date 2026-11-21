"""Translation hook for the packages below the application.

fsbc, fsui and fsgs translate through gettext() here. The application
installs its translation function with initialize_application(); until
then, messages are returned untranslated.
"""

_gettext = None


def set_gettext(function):
    global _gettext
    _gettext = function


def gettext(message):
    if _gettext is None:
        return message
    return _gettext(message)
