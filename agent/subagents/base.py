from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Any

from ..prompt_manager import PromptManager


@dataclass(frozen=True)
class SubAgentMetadata:
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolPermission:
    allowed_tools: Optional[List[str]] = None
    restricted_tools: Optional[List[str]] = None


class RunLLMFn(Protocol):
    def __call__(
        self,
        *,
        system_prompt: str,
        user_input: str,
        permission: ToolPermission,
        enable_thinking: bool,
        thinking_budget: int,
        base_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str: ...


@dataclass
class SubAgentContext:
    run_llm: RunLLMFn
    base_messages: Optional[List[Dict[str, Any]]] = None
    policy_prompt: Optional[str] = None


class BaseSubAgent:
    metadata: SubAgentMetadata
    permission: ToolPermission
    prompt_file: str
    enable_thinking: bool = False
    thinking_budget: int = 4096

    def __init__(self, prompt_manager: Optional[PromptManager] = None):
        self._prompt_manager = prompt_manager or PromptManager.default()
        self._system_prompt: Optional[str] = None

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def triggers(self) -> List[str]:
        return self.metadata.triggers

    @property
    def capabilities(self) -> List[str]:
        return self.metadata.capabilities

    def load_system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = self._prompt_manager.load_prompt(self.prompt_file)
        return self._system_prompt

    def can_handle(self, task: str) -> bool:
        if not task:
            return False
        for t in self.triggers:
            if t and t in task:
                return True
        return False

    def execute(self, task: str, context: SubAgentContext) -> str:
        system_prompt = self.load_system_prompt()
        if context.policy_prompt:
            system_prompt = system_prompt.rstrip() + "\n\n" + context.policy_prompt.strip() + "\n"
        return context.run_llm(
            system_prompt=system_prompt,
            user_input=task,
            permission=self.permission,
            enable_thinking=self.enable_thinking,
            thinking_budget=self.thinking_budget,
            base_messages=context.base_messages,
        )
