import yaml


class Configuration:
    _instance = None

    def __new__(cls, file_path=None, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Configuration, cls).__new__(cls, *args, **kwargs)
            if file_path:
                cls._instance._load_settings(file_path)
        return cls._instance

    def _load_settings(self, file_path):
        with open(file_path, "r") as f:
            self._settings = yaml.safe_load(f)

    @property
    def settings(self):
        return self._settings


def get_config():
    return Configuration().settings
