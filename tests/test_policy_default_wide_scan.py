import unittest

from agent.policy import DefaultPolicy


class TestDefaultPolicyWideScan(unittest.TestCase):
    def test_disallow_wide_glob_by_default(self):
        p = DefaultPolicy()
        state = p.init_state("理解项目结构")
        d = p.validate_tool_call("glob", {"pattern": "**/*"}, state)
        self.assertFalse(d.allowed)

    def test_allow_wide_glob_when_explicit(self):
        p = DefaultPolicy()
        state = p.init_state("请全量扫描全仓库文件")
        d = p.validate_tool_call("glob", {"pattern": "**/*"}, state)
        self.assertTrue(d.allowed)


if __name__ == "__main__":
    unittest.main()

