from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .subagents.base import BaseSubAgent, SubAgentContext


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    output: str


class AgentCoordinator:
    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers

    def _pass_context(
        self,
        previous_output: Optional[str],
        context_factory: Callable[[Optional[str]], SubAgentContext],
    ) -> SubAgentContext:
        return context_factory(previous_output)

    def _aggregate_results(self, results: List[AgentResult]) -> str:
        return self.aggregate_results(results)

    def execute_sequential(
        self,
        steps: List[Tuple[BaseSubAgent, str]],
        context_factory: Callable[[Optional[str]], SubAgentContext],
    ) -> List[AgentResult]:
        results: List[AgentResult] = []
        previous_output: Optional[str] = None
        for agent, task in steps:
            ctx = self._pass_context(previous_output, context_factory)
            out = agent.execute(task, ctx)
            results.append(AgentResult(agent_name=agent.name, output=out))
            previous_output = out
        return results

    def execute_parallel(
        self,
        steps: List[Tuple[BaseSubAgent, str]],
        context_factory: Callable[[Optional[str]], SubAgentContext],
    ) -> List[AgentResult]:
        if not steps:
            return []

        results: List[Optional[AgentResult]] = [None] * len(steps)
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for idx, (agent, task) in enumerate(steps):
                ctx = context_factory(None)
                fut = executor.submit(agent.execute, task, ctx)
                futures[fut] = (idx, agent)

            for fut in as_completed(futures):
                idx, agent = futures[fut]
                try:
                    out = fut.result()
                except Exception as e:
                    out = f"执行失败: {str(e)}"
                results[idx] = AgentResult(agent_name=agent.name, output=out)

        return [r for r in results if r is not None]

    def aggregate_results(self, results: List[AgentResult]) -> str:
        if not results:
            return ""
        parts: List[str] = []
        for r in results:
            parts.append(f"[{r.agent_name}]\n{r.output}".rstrip())
        return "\n\n".join(parts).strip()
