from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class RefactorAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="refactor",
        description="代码重构与结构优化",
        triggers=["重构", "优化", "改进", "清理", "简化", "refactor"],
        capabilities=["refactor", "cleanup", "improve_structure"],
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
            "mkdir",
            "file_delete",
        ],
        restricted_tools=[],
    )
    prompt_file = "refactor_prompt.txt"
    enable_thinking = True

