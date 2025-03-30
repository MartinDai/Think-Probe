import logging

from colorama import init, Fore, Style

# 初始化 colorama（Windows 下需要）
init(autoreset=True)


# 自定义 Formatter 来为不同级别添加颜色
class ColoredFormatter(logging.Formatter):
    # 定义颜色与日志级别的映射
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # 获取对应级别的颜色
        color = self.LEVEL_COLORS.get(record.levelno, Fore.WHITE)
        # 格式化日志消息
        message = super().format(record)
        # 添加颜色并返回
        return color + message + Style.RESET_ALL


# 创建并配置 Handler
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
    force=True
)
logger = logging.getLogger(__name__)
