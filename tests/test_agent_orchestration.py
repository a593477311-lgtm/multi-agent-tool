import os
import unittest


os.environ.setdefault("siliconflow_API_KEY", "test_key")
os.environ.setdefault("siliconflow_BASE_URL", "https://api.siliconflow.cn/v1")


class TestAgentOrchestration(unittest.TestCase):
    def test_agent_initializes_router_and_subagents(self):
        import config
        config.set_platform("siliconflow")

        from agent.agent import Agent
        from agent.router import TaskType

        a = Agent(tools=[], show_reasoning=False, enable_thinking=False)
        ctx = a.memory.build_context()
        system_text = next((m.get("content", "") for m in ctx if m.get("role") == "system"), "")
        self.assertIn("SubAgent", system_text)
        route = a.router.route("理解项目结构")
        self.assertEqual(route.task_type, TaskType.EXPLORE)


if __name__ == "__main__":
    unittest.main()
