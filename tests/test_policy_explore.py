import unittest

from agent.policy import ExplorePolicy
from agent.subagents.base import ToolPermission


class TestExplorePolicy(unittest.TestCase):
    def test_decide_level_l1_for_small_project(self):
        policy = ExplorePolicy()
        state = policy.init_state("请帮我理解项目结构")

        report = "\n".join(
            [
                "📋 项目类型: Python (推测)",
                "📊 统计信息",
                "  目录数量: 2",
                "  文件数量: 3",
            ]
        )

        hint = policy.on_tool_result("project_structure", {}, report, state)
        self.assertIsNone(hint)
        self.assertEqual(state["level"], "L1")

    def test_upgrade_to_l2_for_medium_project(self):
        policy = ExplorePolicy()
        state = policy.init_state("请帮我理解项目结构")

        report = "\n".join(
            [
                "📋 项目类型: Python",
                "📊 统计信息",
                "  目录数量: 30",
                "  文件数量: 80",
            ]
        )

        hint = policy.on_tool_result("project_structure", {}, report, state)
        self.assertEqual(state["level"], "L2")
        self.assertTrue(isinstance(hint, str) and "<decision>" in hint and "<to>L2</to>" in hint)

    def test_reject_wide_glob_in_l1(self):
        policy = ExplorePolicy()
        state = policy.init_state("请帮我理解项目结构")
        decision = policy.validate_tool_call("glob", {"pattern": "**/*"}, state)
        self.assertFalse(decision.allowed)

    def test_early_stop_after_small_project_and_one_file(self):
        policy = ExplorePolicy()
        state = policy.init_state("请帮我理解项目结构")

        report = "\n".join(
            [
                "📋 项目类型: Python (推测)",
                "📊 统计信息",
                "  目录数量: 1",
                "  文件数量: 3",
            ]
        )
        policy.on_tool_result("project_structure", {}, report, state)
        policy.on_tool_result("file_read", {"path": "a.py"}, "文件内容 (a.py):\nprint('x')\n", state)
        self.assertTrue(state.get("should_stop"))
        decision = policy.validate_tool_call("grep", {"pattern": "import"}, state)
        self.assertFalse(decision.allowed)

    def test_effective_permission_changes_by_level(self):
        policy = ExplorePolicy()
        base = ToolPermission(
            allowed_tools=["project_structure", "file_read", "list_dir", "glob", "grep", "dependency", "symbol"],
            restricted_tools=["file_write"],
        )

        state = policy.init_state("请帮我理解项目结构")
        p1 = policy.effective_permission(base, state)
        self.assertEqual(set(p1.allowed_tools or []), {"project_structure", "file_read", "list_dir"})

        state["level"] = "L3"
        p3 = policy.effective_permission(base, state)
        self.assertTrue("symbol" in (p3.allowed_tools or []))


if __name__ == "__main__":
    unittest.main()
