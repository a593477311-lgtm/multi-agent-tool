from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class ReviewerAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="reviewer",
        description="代码审查与风险分析",
        triggers=["审查", "检查", "代码质量", "问题", "优化建议", "review"],
        capabilities=["code_review", "security_review", "quality"],
    )
    permission = ToolPermission(
        allowed_tools=["project_structure", "dependency", "symbol", "glob", "grep", "file_read", "list_dir", "TodoWrite", "project_precheck"],
        restricted_tools=["file_write", "file_delete", "search_replace", "shell_command"],
    )
    prompt_file = "reviewer_prompt.txt"
    enable_thinking = True

