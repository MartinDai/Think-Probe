from datetime import datetime
from zoneinfo import ZoneInfo

from app.config.env_config import get_env_variable


DEFAULT_TIMEZONE = "Asia/Shanghai"


def build_current_time_context() -> str:
    """Build a runtime prompt snippet with the current local time."""
    timezone_name = get_env_variable("APP_TIMEZONE", DEFAULT_TIMEZONE)
    now = datetime.now(ZoneInfo(timezone_name))

    return (
        "\n\n---\n"
        "# Current Time\n"
        f"- 当前本地时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 时区: {timezone_name}\n"
        f"- ISO 8601: {now.isoformat()}\n"
        "涉及 today / tomorrow / 本周 / 截止时间 等相对时间时，"
        "请以上述时间为准进行推断与表达。"
    )
