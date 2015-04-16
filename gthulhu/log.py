import logging

from usm_common.config import UsmConfig
config = UsmConfig()


FORMAT = "%(asctime)s - %(levelname)s - %(name)s %(message)s"
log = logging.getLogger('gthulhu')
handler = logging.FileHandler(config.get('gthulhu', 'log_path'))
handler.setFormatter(logging.Formatter(FORMAT))
log.addHandler(handler)
log.setLevel(logging.getLevelName(config.get('gthulhu', 'log_level')))
