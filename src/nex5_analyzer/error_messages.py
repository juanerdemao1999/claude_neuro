"""User-friendly error message translation for analysis failures.

Converts Python exceptions/tracebacks into actionable guidance in Chinese.
"""

from __future__ import annotations

import re


_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"No spikes? (?:overlap|found|within|in)", re.IGNORECASE),
        "该 Spike 单元在所选 LFP 时间范围内没有放电。\n"
        "建议：检查 Spike 和 LFP 的录制时间段是否重叠，或尝试更换通道组合。",
    ),
    (
        re.compile(r"(?:not enough|too few|insufficient).+spike", re.IGNORECASE),
        "该 Spike 单元的放电次数不足以完成此分析。\n"
        "建议：选择放电频率更高的单元，或减小分析频率以包含更多 spike。",
    ),
    (
        re.compile(r"nperseg.*(?:greater|larger|exceed|>).*(?:length|signal|data)", re.IGNORECASE),
        "FFT 窗口长度 (nperseg) 超过了数据长度。\n"
        "建议：减小 nperseg 参数，或选择更长的 LFP 数据片段。",
    ),
    (
        re.compile(r"(?:empty|no).+(?:data|signal|fragment|segment)", re.IGNORECASE),
        "所选通道的数据为空。\n"
        "建议：确认 NEX5 文件中该通道确实包含有效数据。",
    ),
    (
        re.compile(r"sampling.?rate.*(?:mismatch|differ|inconsist)", re.IGNORECASE),
        "通道之间的采样率不一致。\n"
        "建议：确认参与分析的 LFP 通道具有相同的采样率。",
    ),
    (
        re.compile(r"MemoryError|out of memory", re.IGNORECASE),
        "内存不足，无法完成计算。\n"
        "建议：减小分析的数据长度、降低 nperseg，或关闭其他占用内存的程序。",
    ),
    (
        re.compile(r"IndexError.*(?:out of bounds|index)", re.IGNORECASE),
        "数据索引越界，通常由于数据长度不足或参数设置不匹配。\n"
        "建议：检查参数（如窗口长度、频率范围）是否超出数据范围。",
    ),
    (
        re.compile(r"ZeroDivisionError|division by zero", re.IGNORECASE),
        "计算过程中出现除零错误，通常表示数据为空或参数导致分母为零。\n"
        "建议：检查数据是否有效，尝试调大相关参数。",
    ),
    (
        re.compile(r"(?:FileNotFoundError|No such file)", re.IGNORECASE),
        "找不到指定的文件。\n"
        "建议：确认文件路径正确且文件未被移动或删除。",
    ),
    (
        re.compile(r"Permission(?:Error| denied)", re.IGNORECASE),
        "没有权限读写文件。\n"
        "建议：确认输出目录可写，或尝试以管理员权限运行。",
    ),
    (
        re.compile(r"ValueError.*frequency.*(?:range|band|filter)", re.IGNORECASE),
        "频率范围参数设置无效。\n"
        "建议：确保低频 < 高频，且不超过奈奎斯特频率（采样率的一半）。",
    ),
]


def friendly_error_message(raw_message: str) -> str:
    """Convert a raw exception message/traceback to user-friendly Chinese guidance.

    Returns a clean message without stack traces. If no specific pattern matches,
    extracts the last exception line and wraps it in a generic hint.
    """
    for pattern, friendly in _PATTERNS:
        if pattern.search(raw_message):
            return friendly

    # Extract the actual exception message (last line of traceback or first line)
    lines = raw_message.strip().splitlines()
    # Find the last line that looks like an exception message
    exception_line = lines[0]
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("File ") and not stripped.startswith("Traceback"):
            exception_line = stripped
            break

    # Remove common Python exception prefixes for cleaner display
    for prefix in ("ValueError: ", "RuntimeError: ", "TypeError: ", "KeyError: ", "Exception: "):
        if exception_line.startswith(prefix):
            exception_line = exception_line[len(prefix):]
            break

    return f"分析计算出错：{exception_line}\n建议：检查参数设置是否合理，或尝试更换通道/单元组合。"
