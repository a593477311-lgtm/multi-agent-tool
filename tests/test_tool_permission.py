import unittest

from agent.executor import ToolExecutor
from agent.subagents.base import ToolPermission
from tools.base import Tool


class _OkTool(Tool):
    @property
    def name(self) -> str:
        return "ok_tool"

    @property
    def description(self) -> str:
        return "ok"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs) -> str:
        return "ok"


class TestToolPermission(unittest.TestCase):
    def test_blocks_restricted_tool(self):
        executor = ToolExecutor()
        executor.register_tool(_OkTool())
        executor.set_permission(ToolPermission(allowed_tools=None, restricted_tools=["ok_tool"]))
        results = executor.execute([{"id": "1", "function": {"name": "ok_tool", "arguments": "{}"}}])
        self.assertEqual(results[0]["content"], "错误：无权限使用工具 'ok_tool'")

    def test_allows_allowed_tool(self):
        executor = ToolExecutor()
        executor.register_tool(_OkTool())
        executor.set_permission(ToolPermission(allowed_tools=["ok_tool"], restricted_tools=[]))
        results = executor.execute([{"id": "1", "function": {"name": "ok_tool", "arguments": "{}"}}])
        self.assertEqual(results[0]["content"], "ok")

    def test_blocks_when_allowed_list_present(self):
        executor = ToolExecutor()
        executor.register_tool(_OkTool())
        executor.set_permission(ToolPermission(allowed_tools=[], restricted_tools=[]))
        results = executor.execute([{"id": "1", "function": {"name": "ok_tool", "arguments": "{}"}}])
        self.assertEqual(results[0]["content"], "错误：无权限使用工具 'ok_tool'")


if __name__ == "__main__":
    unittest.main()

