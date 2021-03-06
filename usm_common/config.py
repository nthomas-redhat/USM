import os
import ConfigParser

try:
    import alembic
except ImportError:
    alembic = None
else:
    import alembic.config


class ConfigNotFound(Exception):
    pass


DEFAULT_CONFIG_PATH = "/root/USM/conf/usm.conf"
CONFIG_PATH_VAR = "USM_CONFIG"


class UsmConfig(ConfigParser.SafeConfigParser):
    def __init__(self):
        ConfigParser.SafeConfigParser.__init__(self)

        try:
            self.path = os.environ[CONFIG_PATH_VAR]
        except KeyError:
            self.path = DEFAULT_CONFIG_PATH

        if not os.path.exists(self.path):
            raise ConfigNotFound("Configuration not found at %s" % self.path)

        self.read(self.path)


if alembic is not None:
    class AlembicConfig(alembic.config.Config):
        def __init__(self):
            path = UsmConfig().get('cthulhu', 'alembic_config_path')
            super(AlembicConfig, self).__init__(path)
