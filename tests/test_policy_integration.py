import os
import unittest


os.environ.setdefault("siliconflow_API_KEY", "test_key")
os.environ.setdefault("siliconflow_BASE_URL", "https://api.siliconflow.cn/v1")


class _DeltaFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _ToolCallDelta:
    def __init__(self, index, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class _Delta:
    def __init__(self, content=None, tool_calls=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta):
        self.choices = [_Choice(delta)]


class _LLMStub:
    def __init__(self):
        self.calls = 0
        self.supports_thinking = True
        self.model_id = "stub"

    def stream_completion(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            tc = _ToolCallDelta(
                index=0,
                id="tc1",
                function=_DeltaFunction(name="glob", arguments='{"pattern":"**/*"}'),
            )
            yield _Chunk(_Delta(tool_calls=[tc]))
            return
        yield _Chunk(_Delta(content="ok"))


class _DummyGlobTool:
    @property
    def name(self):
        return "glob"

    @property
    def description(self):
        return "dummy"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}

    def execute(self, **kwargs):
        raise AssertionError("glob should not be executed when policy rejects it")

    def to_openai_tool(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class TestPolicyIntegration(unittest.TestCase):
    def test_policy_rejects_tool_call_and_returns_content(self):
        import config
        config.set_platform("siliconflow")

        from agent.agent import Agent
        from agent.policy import ExplorePolicy
        from agent.subagents.base import ToolPermission

        a = Agent(tools=[_DummyGlobTool()], show_reasoning=False, enable_thinking=False)
        a.llm = _LLMStub()
        a._on_content = lambda *_args, **_kwargs: None
        a._on_reasoning = lambda *_args, **_kwargs: None
        policy = ExplorePolicy()
        state = policy.init_state("理解项目结构")

        out = a._run_subagent_conversation(
            system_prompt="x",
            user_input="理解项目结构",
            permission=ToolPermission(allowed_tools=["glob"], restricted_tools=[]),
            enable_thinking=False,
            thinking_budget=0,
            base_messages=None,
            record_changes=False,
            policy=policy,
            policy_state=state,
        )
        self.assertEqual(out, "ok")


if __name__ == "__main__":
    unittest.main()
