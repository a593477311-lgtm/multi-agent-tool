import unittest

from agent.coordinator import AgentCoordinator
from agent.router import AgentRouter, TaskType
from agent.subagents.base import BaseSubAgent, SubAgentMetadata, ToolPermission, SubAgentContext


class _SubAgent(BaseSubAgent):
    def __init__(self, name: str, triggers, prompt_manager=None):
        self.metadata = SubAgentMetadata(
            name=name,
            description=name,
            triggers=list(triggers),
            capabilities=[],
        )
        self.permission = ToolPermission(allowed_tools=["file_read"], restricted_tools=["file_write"])
        self.prompt_file = "dummy_prompt.txt"
        super().__init__(prompt_manager=prompt_manager)


class TestAgentRouter(unittest.TestCase):
    def test_routes_to_registered_agent(self):
        router = AgentRouter()
        explore = _SubAgent("explore", triggers=["理解项目"])
        router.register(TaskType.EXPLORE, explore)

        result = router.route("请帮我理解项目结构")
        self.assertEqual(result.task_type, TaskType.EXPLORE)
        self.assertIs(result.subagent, explore)

    def test_general_when_no_match(self):
        router = AgentRouter()
        result = router.route("随便聊聊")
        self.assertEqual(result.task_type, TaskType.GENERAL)


class TestAgentCoordinator(unittest.TestCase):
    def test_execute_sequential_passes_previous_output(self):
        coordinator = AgentCoordinator()

        class A(_SubAgent):
            def execute(self, task: str, context: SubAgentContext) -> str:
                return "a"

        class B(_SubAgent):
            def execute(self, task: str, context: SubAgentContext) -> str:
                base = context.base_messages
                return "b" if base is None else "b2"

        a = A("a", triggers=["a"])
        b = B("b", triggers=["b"])

        def context_factory(prev):
            base_messages = None if prev is None else [{"role": "assistant", "content": prev}]
            return SubAgentContext(run_llm=lambda **_: "", base_messages=base_messages)

        results = coordinator.execute_sequential([(a, "t1"), (b, "t2")], context_factory)
        self.assertEqual([r.output for r in results], ["a", "b2"])

    def test_execute_parallel_keeps_order(self):
        coordinator = AgentCoordinator(max_workers=2)
        a = _SubAgent("a", triggers=["a"])
        b = _SubAgent("b", triggers=["b"])

        def context_factory(_):
            return SubAgentContext(run_llm=lambda **_: "ok", base_messages=None)

        results = coordinator.execute_parallel([(a, "t1"), (b, "t2")], context_factory)
        self.assertEqual([r.agent_name for r in results], ["a", "b"])

        aggregated = coordinator.aggregate_results(results)
        self.assertIn("[a]", aggregated)
        self.assertIn("[b]", aggregated)


if __name__ == "__main__":
    unittest.main()

