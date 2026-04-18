import unittest

from agent.prompt_manager import PromptManager
from agent.subagents import (
    ExploreAgent,
    DebuggerAgent,
    ArchitectAgent,
    ReviewerAgent,
    TestAgent,
    RefactorAgent,
)


class TestSubAgents(unittest.TestCase):
    def test_prompt_files_exist(self):
        pm = PromptManager.default()
        for cls in [ExploreAgent, DebuggerAgent, ArchitectAgent, ReviewerAgent, TestAgent, RefactorAgent]:
            a = cls(prompt_manager=pm)
            content = a.load_system_prompt()
            self.assertTrue(isinstance(content, str))
            self.assertTrue(len(content) > 0)


if __name__ == "__main__":
    unittest.main()

