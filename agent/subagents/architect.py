from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class ArchitectAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="architect",
        description="架构与 API 设计建议",
        triggers=["设计", "架构", "API", "技术选型", "方案", "模块划分"],
        capabilities=["architecture", "api_design", "planning"],
    )
    permission = ToolPermission(
        allowed_tools=["project_structure", "dependency", "symbol", "glob", "grep", "file_read", "list_dir", "TodoWrite", "project_precheck"],
        restricted_tools=["file_write", "file_delete", "search_replace", "shell_command"],
    )
    prompt_file = "architect_prompt.txt"
    enable_thinking = True

