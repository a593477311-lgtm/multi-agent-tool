import unittest

from agent.policy import RefactorPolicy
from agent.subagents.base import ToolPermission


class TestRefactorPolicyHandoff(unittest.TestCase):
    def test_deny_reread_file_in_handoff(self):
        p = RefactorPolicy()
        state = p.init_state("请帮我改进项目")
        state["handoff"] = {"read_files": ["app.py"]}

        d1 = p.validate_tool_call("file_read", {"path": "app.py"}, state)
        self.assertFalse(d1.allowed)

        d2 = p.validate_tool_call("file_read", {"path": "app.py", "allow_reread": True}, state)
        self.assertTrue(d2.allowed)

    def test_deny_shell_command_by_default(self):
        p = RefactorPolicy()
        state = p.init_state("请帮我重构项目")
        d = p.validate_tool_call("shell_command", {"command": "python -V"}, state)
        self.assertFalse(d.allowed)

    def test_allow_shell_command_when_explicit(self):
        p = RefactorPolicy()
        state = p.init_state("请运行项目并验证")
        d1 = p.validate_tool_call("shell_command", {"command": "python -V"}, state)
        self.assertTrue(d1.allowed)
        d2 = p.validate_tool_call("shell_command", {"command": "python -V"}, state)
        self.assertFalse(d2.allowed)

    def test_handoff_only_removes_tools(self):
        p = RefactorPolicy()
        state = p.init_state("请给出重构计划")
        state["handoff_only"] = True
        base = ToolPermission(allowed_tools=["file_read", "grep"], restricted_tools=["file_write"])
        eff = p.effective_permission(base, state)
        self.assertEqual(eff.allowed_tools, [])


if __name__ == "__main__":
    unittest.main()

