from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class DebuggerAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="debugger",
        description="错误诊断与修复执行",
        triggers=["报错", "bug", "修复", "错误", "调试", "失败", "traceback", "exception"],
        capabilities=["debug", "fix", "root_cause"],
    )
    permission = ToolPermission(
        allowed_tools=[
            "file_read",
            "file_write",
            "search_replace",
            "glob",
            "grep",
            "shell_command",
            "list_dir",
            "TodoWrite",
            "http_request",
        ],
        restricted_tools=["file_delete"],
    )
    prompt_file = "debugger_prompt.txt"
    enable_thinking = True

