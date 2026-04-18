import unittest
from pathlib import Path

from agent.prompt_manager import PromptManager
from agent.subagents.base import BaseSubAgent, SubAgentMetadata, ToolPermission, SubAgentContext


class _DummyAgent(BaseSubAgent):
    metadata = SubAgentMetadata(
        name="dummy",
        description="dummy",
        triggers=["hello", "world"],
        capabilities=["test"],
    )
    permission = ToolPermission(allowed_tools=["file_read"], restricted_tools=["file_write"])
    prompt_file = "dummy_prompt.txt"


class TestPromptManager(unittest.TestCase):
    def test_load_prompt_caches(self):
        tmp_dir = Path(__file__).parent / "_tmp_prompts"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            (tmp_dir / "a.txt").write_text("x", encoding="utf-8")
            pm = PromptManager(base_dir=tmp_dir)
            self.assertEqual(pm.load_prompt("a.txt"), "x")
            (tmp_dir / "a.txt").write_text("y", encoding="utf-8")
            self.assertEqual(pm.load_prompt("a.txt"), "x")
        finally:
            for p in tmp_dir.glob("*"):
                p.unlink()
            tmp_dir.rmdir()


class TestBaseSubAgent(unittest.TestCase):
    def test_can_handle_by_triggers(self):
        tmp_dir = Path(__file__).parent / "_tmp_prompts2"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            (tmp_dir / "dummy_prompt.txt").write_text("prompt", encoding="utf-8")
            agent = _DummyAgent(prompt_manager=PromptManager(base_dir=tmp_dir))
            self.assertTrue(agent.can_handle("say hello"))
            self.assertTrue(agent.can_handle("world peace"))
            self.assertFalse(agent.can_handle("no match"))
        finally:
            for p in tmp_dir.glob("*"):
                p.unlink()
            tmp_dir.rmdir()

    def test_execute_uses_runner(self):
        tmp_dir = Path(__file__).parent / "_tmp_prompts3"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            (tmp_dir / "dummy_prompt.txt").write_text("prompt", encoding="utf-8")
            agent = _DummyAgent(prompt_manager=PromptManager(base_dir=tmp_dir))

            def run_llm(**kwargs):
                return f"{kwargs['system_prompt']}|{kwargs['user_input']}"

            ctx = SubAgentContext(run_llm=run_llm, base_messages=None)
            self.assertEqual(agent.execute("task", ctx), "prompt|task")
        finally:
            for p in tmp_dir.glob("*"):
                p.unlink()
            tmp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

