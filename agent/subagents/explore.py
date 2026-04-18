from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class ExploreAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="explore",
        description="项目理解与结构分析",
        triggers=["理解项目", "分析代码", "项目结构", "目录结构", "入口", "工作流程", "这个模块"],
        capabilities=["project_structure", "dependency_analysis", "code_navigation"],
    )
    permission = ToolPermission(
        allowed_tools=["project_structure", "dependency", "symbol", "glob", "grep", "file_read", "list_dir", "TodoWrite"],
        restricted_tools=["file_write", "file_delete", "search_replace", "shell_command"],
    )
    prompt_file = "explore_prompt.txt"
    enable_thinking = True

