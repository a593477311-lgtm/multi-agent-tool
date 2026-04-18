from typing import Dict, Any
from .base import Tool


class SubagentTool(Tool):
    @property
    def name(self) -> str:
        return "use_subagent"

    @property
    def description(self) -> str:
        return (
            "调用专门的子代理来处理特定类型的任务。"
            "当你判断用户任务需要特定专业能力时使用此工具。"
            "可用子代理：explore(项目理解)、debugger(错误修复)、architect(架构设计)、"
            "reviewer(代码审查)、test(测试)、refactor(重构)。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subagent_name": {
                    "type": "string",
                    "description": (
                        "要调用的子代理名称。可选值："
                        "explore(项目理解与结构分析)、"
                        "debugger(错误诊断与修复)、"
                        "architect(架构与API设计)、"
                        "reviewer(代码审查与风险分析)、"
                        "test(测试用例生成与执行)、"
                        "refactor(代码重构与结构优化)"
                    ),
                    "enum": ["explore", "debugger", "architect", "reviewer", "test", "refactor"],
                },
                "reason": {
                    "type": "string",
                    "description": "调用该子代理的原因，说明为什么这个任务适合由该子代理处理",
                },
                "task": {
                    "type": "string",
                    "description": "要传递给子代理的具体任务描述（可选，默认使用用户原始输入）",
                },
            },
            "required": ["subagent_name"],
        }

    def execute(self, **kwargs) -> str:
        subagent_name = kwargs.get("subagent_name", "")
        reason = kwargs.get("reason", "")
        task = kwargs.get("task", "")
        
        return f"[SUBAGENT_CALL]{subagent_name}|{reason}|{task}[/SUBAGENT_CALL]"
