from pathlib import Path

import yaml

from app.utils.logger import logger

# 运行时目录
RUNTIME_DIR = Path.cwd()


class ConfigLoader:
    """配置加载器类"""

    def __init__(self):
        self.config = {}
        self.load_config()

    def load_config(self):
        """加载 YAML 格式的配置文件"""
        runtime_config = RUNTIME_DIR / "config.yml"
        if runtime_config.exists():
            try:
                with open(runtime_config, 'r', encoding='utf-8') as f:
                    runtime_conf = yaml.safe_load(f)
                    if runtime_conf:
                        self.config.update(runtime_conf)
                        logger.info(f"Loaded runtime config from: {runtime_config}")
            except Exception as e:
                logger.error(f"Failed to load runtime config: {e}")
        else:
            logger.warning(f"config file not found at: {runtime_config}")

    def get(self, key, default=None):
        """获取配置值"""
        return self.config.get(key, default)


config = ConfigLoader()

on_debug = True == config.get("debug")

# 打印配置内容
logger.info("Config contents:")
for key, value in config.config.items():
    logger.info(f"{key}: {value}")
