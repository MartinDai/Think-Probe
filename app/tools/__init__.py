import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult(object):
    success: bool
    result: Any

def parse_tool_result_safe(text: str) -> ToolResult:
    try:
        # 使用正则表达式提取 success 和 result
        match = re.match(r"ToolResult\(success=(True|False), result=(.*)\)", text)
        if not match:
            raise ValueError("字符串格式不正确")
        success = match.group(1) == "True"
        result_str = match.group(2)
        # 安全解析 result
        result = ast.literal_eval(result_str)
        return ToolResult(success=success, result=result)
    except (ValueError, SyntaxError, TypeError) as e:
        raise ValueError(f"无法解析字符串为 ToolResult 对象: {e}")

if __name__ == "__main__":
    print(parse_tool_result_safe("ToolResult(success=True, result='hello world')"))