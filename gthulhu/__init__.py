from usm_common.salt_wrapper import client_config
from usm_common.config import UsmConfig

# A config instance for use from within the manager service
config = UsmConfig()

# A salt config instance for places we'll need the sock_dir
salt_config = client_config(config.get('gthulhu', 'salt_config_path'))
