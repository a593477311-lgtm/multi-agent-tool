from __future__ import annotations

from .base import BaseSubAgent, SubAgentMetadata, ToolPermission


class TestAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="test",
        description="测试用例生成与执行",
        triggers=["测试", "test", "单元测试", "测试用例", "覆盖率"],
        capabilities=["testing", "test_generation", "test_execution"],
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
        ],
        restricted_tools=["file_delete"],
    )
    prompt_file = "test_prompt.txt"
    enable_thinking = True

