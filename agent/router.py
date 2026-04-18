from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .subagents.base import BaseSubAgent


class TaskType(Enum):
    EXPLORE = "explore"
    DEBUG = "debug"
    ARCHITECT = "architect"
    REVIEW = "review"
    TEST = "test"
    REFACTOR = "refactor"
    GENERAL = "general"


@dataclass(frozen=True)
class RouteResult:
    task_type: TaskType
    subagent: Optional[BaseSubAgent] = None
    collaboration: Optional[List[TaskType]] = None


class AgentRouter:
    def __init__(self):
        self._subagents: Dict[TaskType, List[BaseSubAgent]] = {}

    def register(self, task_type: TaskType, subagent: BaseSubAgent) -> None:
        self._subagents.setdefault(task_type, []).append(subagent)

    def _analyze_task_type(self, task: str) -> TaskType:
        if not task:
            return TaskType.GENERAL

        keywords: List[Tuple[TaskType, List[str]]] = [
            (TaskType.EXPLORE, ["理解项目", "分析代码", "项目结构", "目录结构", "入口", "工作流程"]),
            (TaskType.DEBUG, ["报错", "bug", "修复", "错误", "调试", "失败", "exception", "traceback"]),
            (TaskType.ARCHITECT, ["设计", "架构", "API", "技术选型", "方案", "模块划分"]),
            (TaskType.REVIEW, ["审查", "检查", "代码质量", "问题", "优化建议", "review"]),
            (TaskType.TEST, ["测试", "test", "单元测试", "测试用例", "覆盖率"]),
            (TaskType.REFACTOR, ["重构", "优化", "改进", "清理", "简化", "refactor"]),
        ]

        for ttype, keys in keywords:
            for k in keys:
                if k and k in task:
                    return ttype

        for ttype, agents in self._subagents.items():
            for a in agents:
                if a.can_handle(task):
                    return ttype

        return TaskType.GENERAL

    def detect_collaboration(self, task: str) -> List[TaskType]:
        if not task:
            return []

        hits: List[TaskType] = []
        for ttype in [
            TaskType.EXPLORE,
            TaskType.DEBUG,
            TaskType.ARCHITECT,
            TaskType.REVIEW,
            TaskType.TEST,
            TaskType.REFACTOR,
        ]:
            agents = self._subagents.get(ttype, [])
            if any(a.can_handle(task) for a in agents):
                hits.append(ttype)

        if len(hits) <= 1:
            analyzed = self._analyze_task_type(task)
            return [] if analyzed == TaskType.GENERAL else [analyzed]

        return hits

    def route(self, task: str) -> RouteResult:
        task_type = self._analyze_task_type(task)
        collaboration = self.detect_collaboration(task)

        if task_type == TaskType.GENERAL:
            return RouteResult(
                task_type=TaskType.GENERAL,
                subagent=None,
                collaboration=collaboration or None,
            )

        agents = self._subagents.get(task_type, [])
        chosen = None
        for a in agents:
            if a.can_handle(task):
                chosen = a
                break
        if chosen is None and agents:
            chosen = agents[0]

        return RouteResult(
            task_type=task_type,
            subagent=chosen,
            collaboration=collaboration or None,
        )
