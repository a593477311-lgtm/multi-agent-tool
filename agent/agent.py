from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import json
import re
from .llm import LLMClient
from .memory import Memory
from .change_history import ChangeHistory
from .executor import ToolExecutor
from .reasoning_handler import ReasoningHandler
from tools.base import Tool
from utils.logger import get_logger
from utils.stream_handler import StreamHandler
from config import get_work_dir, get_sessions_dir
from config.models import get_model_config, get_all_models, model_exists, get_model_price
from .router import AgentRouter, TaskType, RouteResult
from .coordinator import AgentCoordinator
from .subagents import (
    BaseSubAgent,
    SubAgentContext,
    ToolPermission,
    ExploreAgent,
    DebuggerAgent,
    ArchitectAgent,
    ReviewerAgent,
    TestAgent,
    RefactorAgent,
)
from .policy import (
    SubAgentPolicy,
    DefaultPolicy,
    ExplorePolicy,
    DebuggerPolicy,
    ReviewerPolicy,
    TestPolicy,
    RefactorPolicy,
    ArchitectPolicy,
)

logger = get_logger()
DEBUG = True

class TaskState(Enum):
    COMPLETED = "completed"
    CONTINUE = "continue"
    NEEDS_INPUT = "needs_input"
    ERROR = "error"

@dataclass
class FollowUpState:
    pending: bool = False
    reason: str = ""
    remaining_tasks: List[str] = field(default_factory=list)
    iteration_count: int = 0
    max_safe_iterations: int = 50

class Agent:
    def __init__(
        self,
        tools: Optional[List[Tool]] = None,
        system_prompt: Optional[str] = None,
        show_reasoning: bool = True,
        enable_thinking: bool = True,
        model_id: Optional[str] = None,
        callbacks: Optional[Dict[str, Callable]] = None,
    ):
        self.llm = LLMClient(model_id=model_id)
        self.memory = Memory()
        self.executor = ToolExecutor()
        self.reasoning_handler = ReasoningHandler(show_reasoning=show_reasoning)
        self.conversation_log: List[Dict] = []
        self.session_start_time = datetime.now()
        self.enable_thinking = enable_thinking if self.llm.supports_thinking else False
        self.thinking_budget = 4096
        self.change_history = ChangeHistory()
        self.followup_state = FollowUpState()
        self.input_tokens_used: int = 0
        self.output_tokens_used: int = 0
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0
        self.callbacks = callbacks or {}
        self.router = AgentRouter()
        self.coordinator = AgentCoordinator()
        self._subagents: Dict[TaskType, List[BaseSubAgent]] = {}
        self.ui_expanded: bool = False
        
        if tools:
            self.executor.register_tools(tools)

        self._register_default_subagents()
        
        if system_prompt:
            self.memory.set_system_prompt(system_prompt)
        else:
            self._load_default_system_prompt()
        
        logger.info(f"Agent 初始化完成，模型: {self.llm.model_id}")

    def set_ui_mode(self, expanded: bool) -> None:
        self.ui_expanded = bool(expanded)

    def _register_default_subagents(self) -> None:
        instances: List[tuple[TaskType, BaseSubAgent]] = [
            (TaskType.EXPLORE, ExploreAgent()),
            (TaskType.DEBUG, DebuggerAgent()),
            (TaskType.ARCHITECT, ArchitectAgent()),
            (TaskType.REVIEW, ReviewerAgent()),
            (TaskType.TEST, TestAgent()),
            (TaskType.REFACTOR, RefactorAgent()),
        ]
        for ttype, agent in instances:
            self._subagents.setdefault(ttype, []).append(agent)
            self.router.register(ttype, agent)
    
    def _load_default_system_prompt(self) -> None:
        model_id = self.llm.model_id
        safe_model_id = model_id.replace("/", "_")
        
        prompts_dir = Path(__file__).parent.parent / "prompts"
        
        prompt_filename = f"{safe_model_id}_system_prompt_en.txt"
        prompt_path = prompts_dir / prompt_filename
        
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.memory.set_system_prompt(self._augment_system_prompt(f.read()))
            return
        
        prompt_filename = f"{safe_model_id}_system_prompt.txt"
        prompt_path = prompts_dir / prompt_filename
        
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.memory.set_system_prompt(self._augment_system_prompt(f.read()))
            return
        
        lower_filename = f"{safe_model_id.lower()}_system_prompt.txt"
        for existing_file in prompts_dir.glob("*_system_prompt.txt"):
            if existing_file.name.lower() == lower_filename:
                with open(existing_file, "r", encoding="utf-8") as f:
                    self.memory.set_system_prompt(self._augment_system_prompt(f.read()))
                return
        
        if "deepseek" in model_id.lower():
            deepseek_prompt = prompts_dir / "deepseek-ai_DeepSeek-V3.2_system_prompt.txt"
            if deepseek_prompt.exists():
                with open(deepseek_prompt, "r", encoding="utf-8") as f:
                    self.memory.set_system_prompt(self._augment_system_prompt(f.read()))
                return
        
        default_path = prompts_dir / "system_prompt.txt"
        if default_path.exists():
            with open(default_path, "r", encoding="utf-8") as f:
                self.memory.set_system_prompt(self._augment_system_prompt(f.read()))
        else:
            default_prompt = "You are an intelligent assistant that can help users complete various tasks."
            self.memory.set_system_prompt(self._augment_system_prompt(default_prompt))

    def _augment_system_prompt(self, base_prompt: str) -> str:
        base = (base_prompt or "").rstrip()
        
        subagent_info = self._build_subagent_info()
        
        capability = (
            "\n\n---\n\n"
            "<capabilities>\n"
            "  <guards>执行期会强制工具权限与策略约束；不要假设自己总能使用所有工具。</guards>\n"
            "</capabilities>\n"
        )
        
        if subagent_info:
            capability = (
                "\n\n---\n\n"
                "<capabilities>\n"
                f"{subagent_info}\n"
                "  <guards>执行期会强制工具权限与策略约束；不要假设自己总能使用所有工具。</guards>\n"
                "</capabilities>\n"
            )
        
        return base + capability
    
    def _build_subagent_info(self) -> str:
        subagent_descriptions = {
            "explore": {
                "description": "项目理解与结构分析专家",
                "when_to_use": "用户想了解项目结构、入口、工作流程、模块职责时使用。只读分析，不修改代码。"
            },
            "debugger": {
                "description": "错误诊断与修复专家",
                "when_to_use": "用户遇到报错、bug、异常，需要定位问题并修复时使用。会修改代码。"
            },
            "architect": {
                "description": "架构与API设计专家",
                "when_to_use": "用户需要设计新模块、API接口、技术选型建议时使用。只读分析，不修改代码。"
            },
            "reviewer": {
                "description": "代码审查与风险分析专家",
                "when_to_use": "用户需要代码质量检查、安全审查、性能分析时使用。只读分析，不修改代码。"
            },
            "test": {
                "description": "测试用例生成与执行专家",
                "when_to_use": "用户需要编写单元测试、集成测试、测试覆盖率分析时使用。会创建测试文件。"
            },
            "refactor": {
                "description": "代码重构与结构优化专家",
                "when_to_use": "用户明确要求重构代码、优化代码结构、清理技术债务时使用。会修改代码。注意：仅'理解项目'或'了解'不应触发此子代理。"
            }
        }
        
        lines = ['  <available_subagents>']
        for name, info in subagent_descriptions.items():
            lines.append(f'    <subagent name="{name}">')
            lines.append(f'      <description>{info["description"]}</description>')
            lines.append(f'      <when_to_use>{info["when_to_use"]}</when_to_use>')
            lines.append('    </subagent>')
        lines.append('  </available_subagents>')
        
        return '\n'.join(lines)
    
    def get_current_model(self) -> str:
        return self.llm.model_id
    
    def get_model_display_name(self) -> str:
        model_config = get_model_config(self.llm.model_id)
        if model_config:
            return model_config.display_name
        return self.llm.model_id
    
    def get_total_cost(self) -> float:
        prices = get_model_price(self.llm.model_id)
        input_cost = (self.input_tokens_used / 1_000_000) * prices["input"]
        output_cost = (self.output_tokens_used / 1_000_000) * prices["output"]
        return input_cost + output_cost
    
    def get_token_usage(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens_used,
            "output_tokens": self.output_tokens_used,
        }
    
    def switch_model(self, model_id: str) -> bool:
        if not model_exists(model_id):
            return False
        
        if self.llm.switch_model(model_id):
            self._load_default_system_prompt()
            model_config = get_model_config(model_id)
            if model_config and not model_config.supports_thinking:
                self.enable_thinking = False
            logger.info(f"模型已切换: {model_id}")
            return True
        return False
    
    def get_available_models(self) -> List[Dict]:
        return [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "supports_thinking": m.supports_thinking,
                "is_current": m.model_id == self.llm.model_id
            }
            for m in get_all_models()
        ]
    
    def register_tool(self, tool: Tool) -> None:
        self.executor.register_tool(tool)
    
    def run(self, user_input: str) -> str:
        logger.info(f"用户输入: {user_input}")
        
        self.memory.add_user_message(user_input)
        
        response = self._process_with_llm_routing(user_input)
        
        if response:
            self.memory.add_assistant_message(content=response)
        
        return response

    def _process_with_llm_routing(self, user_input: str) -> str:
        messages = self.memory.build_context(task_type="main")
        tools = self.executor.get_tool_definitions()
        
        def _filtered_tool_call_handler(tool_call: dict):
            tool_name = tool_call.get('function', {}).get('name', '')
            if tool_name == 'use_subagent':
                return
            if 'tool_call' in self.callbacks:
                self._emit('tool_call', tool_name=tool_name, args={})
            else:
                print(f"\n\033[33m[工具调用] {tool_name}\033[0m")
        
        stream_handler = StreamHandler(
            on_reasoning=self._on_reasoning,
            on_content=self._on_content,
            on_tool_call=_filtered_tool_call_handler,
        )
        
        try:
            stream = self.llm.stream_completion(
                messages=messages,
                tools=tools if tools else None,
                enable_thinking=self.enable_thinking,
                thinking_budget=self.thinking_budget,
            )
            
            for chunk in stream:
                stream_handler.process_chunk(chunk)
            
            state = stream_handler.finalize()
            
            if state.input_tokens == 0:
                state.input_tokens = self.memory.get_token_count()
            
            self.input_tokens_used += state.input_tokens
            self.output_tokens_used += state.output_tokens
            self._last_input_tokens = state.input_tokens
            self._last_output_tokens = state.output_tokens
            
        except Exception as e:
            logger.error(f"LLM 调用失败: {str(e)}")
            return f"抱歉，处理请求时发生错误: {str(e)}"
        
        self.reasoning_handler.end_reasoning_block()
        
        tool_calls = state.tool_calls
        content = state.content
        reasoning = state.reasoning_content
        
        subagent_call = self._extract_subagent_call(tool_calls)
        
        if subagent_call:
            subagent_name = subagent_call.get("subagent_name", "")
            reason = subagent_call.get("reason", "")
            task = subagent_call.get("task", "") or user_input
            
            self._log_routing_decision("llm", subagent_name, reason or "主模型判断")
            
            if 'subagent_call' in self.callbacks:
                self._emit('subagent_call', name=subagent_name, reason=reason)
            else:
                print(f"\n🧩 调用子Agent：{subagent_name}")
                if reason:
                    print(f"   原因：{reason}")
            
            result = self._execute_subagent_by_name(subagent_name, task)
            return result
        
        if tool_calls and len(tool_calls) > 0:
            return self._handle_tool_calls(tool_calls, content, reasoning)
        
        return content or ""

    def _extract_subagent_call(self, tool_calls: List[Dict]) -> Optional[Dict[str, str]]:
        if not tool_calls:
            return None
        
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            if tool_name == "use_subagent":
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                    return {
                        "subagent_name": args.get("subagent_name", ""),
                        "reason": args.get("reason", ""),
                        "task": args.get("task", ""),
                    }
                except json.JSONDecodeError:
                    return None
        return None

    def _execute_subagent_by_name(self, subagent_name: str, task: str) -> str:
        from .router import TaskType
        
        task_type_map = {
            "explore": TaskType.EXPLORE,
            "debugger": TaskType.DEBUG,
            "architect": TaskType.ARCHITECT,
            "reviewer": TaskType.REVIEW,
            "test": TaskType.TEST,
            "refactor": TaskType.REFACTOR,
        }
        
        task_type = task_type_map.get(subagent_name)
        if not task_type:
            return f"未知的子代理：{subagent_name}"
        
        agents = self._subagents.get(task_type, [])
        if not agents:
            return f"未找到子代理：{subagent_name}"
        
        subagent = agents[0]
        
        if 'subagent_start' in self.callbacks:
            self._emit('subagent_start', name=subagent.name)
        else:
            print(f"\n� 当前子Agent：{subagent.name}\n", end="")
        
        policy = self._get_policy_for_subagent(subagent)
        policy_state = policy.init_state(task)
        
        if 'stage' in self.callbacks:
            self._emit('stage', stage=policy.stage_label(policy_state))
        else:
            print(f"📍 策略阶段：{policy.stage_label(policy_state)}\n", end="")
        
        base_messages = self._build_subagent_base_messages(max_messages=12)
        
        def make_runner(record_changes: bool, policy: SubAgentPolicy, policy_state: Dict[str, Any], subagent_name: str = None):
            def _run(**kwargs):
                return self._run_subagent_conversation(
                    record_changes=record_changes,
                    policy=policy,
                    policy_state=policy_state,
                    subagent_name=subagent_name,
                    **kwargs,
                )
            return _run
        
        record_changes = subagent.name == "refactor"
        ctx = SubAgentContext(
            run_llm=make_runner(record_changes, policy, policy_state, subagent.name),
            base_messages=base_messages,
            policy_prompt=f"<ui><mode>{'expanded' if self.ui_expanded else 'collapsed'}</mode></ui>\n" + policy.policy_prompt(policy_state),
        )
        
        return subagent.execute(task, ctx)

    def _handle_tool_calls(self, tool_calls: List[Dict], content: Optional[str], reasoning: Optional[str]) -> str:
        valid_tool_calls = []
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            tc_func = tc.get("function", {})
            tc_name = tc_func.get("name", "")
            
            if tc_name == "use_subagent":
                continue
            
            if tc_name and tc_id:
                valid_tool_calls.append(tc)
        
        if not valid_tool_calls:
            return content or ""
        
        formatted_tool_calls = self._format_tool_calls_for_memory(valid_tool_calls)
        
        assistant_msg = {"role": "assistant", "tool_calls": formatted_tool_calls}
        if content and content.strip():
            assistant_msg["content"] = content
        if reasoning and reasoning.strip():
            assistant_msg["reasoning_content"] = reasoning
        self.memory.messages.append(assistant_msg)
        
        for tc in valid_tool_calls:
            tool_name = tc.get("function", {}).get("name", "unknown")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if args_str else {}
            except:
                args = {}
            if 'tool_call' in self.callbacks:
                self._emit('tool_call', tool_name=tool_name, args=args)
            else:
                print(f"\n\033[33m  📌 {tool_name}\033[0m")
                if args:
                    print(f"\033[90m     参数: {json.dumps(args, ensure_ascii=False)}\033[0m")
        
        results = self.executor.execute(valid_tool_calls)
        
        for result in results:
            tool_name = "unknown"
            for tc in valid_tool_calls:
                if tc.get("id") == result["tool_call_id"]:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    break
            args_str = "{}"
            for tc in valid_tool_calls:
                if tc.get("id") == result["tool_call_id"]:
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    break
            try:
                args = json.loads(args_str) if args_str else {}
            except:
                args = {}
            if 'tool_result' in self.callbacks:
                self._emit('tool_result', tool_name=tool_name, result=result['content'], args=args)
            self.memory.add_tool_result(
                tool_call_id=result["tool_call_id"],
                content=result["content"]
            )
        
        return self._process_conversation()

    def _log_routing_decision(self, decision_type: str, subagent: str, reason: str) -> None:
        logger.info(f"路由决策: type={decision_type}, subagent={subagent}, reason={reason}")
        self.memory.add_knowledge("routing_decision", {
            "decision_type": decision_type,
            "subagent": subagent,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

    def _should_use_subagent(self, route: RouteResult) -> bool:
        return route.task_type != TaskType.GENERAL and route.subagent is not None

    def _dispatch_to_subagent(self, task: str, route: RouteResult) -> str:
        base_messages = self._build_subagent_base_messages(max_messages=12)

        def make_runner(record_changes: bool, policy: SubAgentPolicy, policy_state: Dict[str, Any], subagent_name: str = None):
            def _run(**kwargs):
                return self._run_subagent_conversation(
                    record_changes=record_changes,
                    policy=policy,
                    policy_state=policy_state,
                    subagent_name=subagent_name,
                    **kwargs,
                )
            return _run

        if route.collaboration and len(route.collaboration) > 1:
            chain = " -> ".join([t.value for t in route.collaboration])
            previous_output: Optional[str] = None
            previous_handoff: Optional[Dict[str, Any]] = None
            outputs: List[str] = []
            for ttype in route.collaboration:
                agents = self._subagents.get(ttype, [])
                if not agents:
                    continue
                agent = agents[0]
                policy = self._get_policy_for_subagent(agent)
                policy_state = policy.init_state(task)
                if previous_handoff is not None:
                    policy_state["handoff"] = previous_handoff
                msgs = list(base_messages)
                if previous_output:
                    msgs.append({"role": "assistant", "content": previous_output})
                if 'subagent_start' in self.callbacks:
                    self._emit('subagent_start', name=agent.name)
                else:
                    print(f"\n🧩 当前子Agent：{agent.name}\n", end="")
                if 'stage' in self.callbacks:
                    self._emit('stage', stage=policy.stage_label(policy_state))
                else:
                    print(f"📍 策略阶段：{policy.stage_label(policy_state)}\n", end="")

                ui_mode_xml = f"<ui><mode>{'expanded' if self.ui_expanded else 'collapsed'}</mode></ui>\n"
                handoff_xml = self._handoff_to_xml(previous_handoff) if previous_handoff else ""
                ctx = SubAgentContext(
                    run_llm=make_runner(False, policy, policy_state, agent.name),
                    base_messages=msgs,
                    policy_prompt=ui_mode_xml + policy.policy_prompt(policy_state) + ("\n" + handoff_xml if handoff_xml else ""),
                )
                step_task = task
                if agent.name == "explore" and not self.ui_expanded:
                    step_task = (
                        "请输出短摘要（总计不超过 18 行，每段不超过 5 条要点）。\n"
                        "不要写论文式长文；细节以“待补证据清单”列出。\n"
                        "如用户需要详细版，提示可用 /expand 或明确要求“详细/展开”。\n\n"
                        f"用户需求：{task}"
                    )
                if agent.name == "refactor" and previous_handoff and previous_handoff.get("from_agent") == "explore":
                    if previous_handoff.get("early_stop") and self._is_improvement_prep(task):
                        policy_state["handoff_only"] = True
                        step_task = (
                            "基于以下交接单输出：重构计划/风险清单/最小改动路径。\n"
                            "要求：不要继续读取项目文件或执行命令；如果信息不足，只列出需要补的证据清单。\n\n"
                            + handoff_xml
                        )

                out = agent.execute(step_task, ctx)
                outputs.append(f"[{agent.name}]\n{out}".rstrip())
                previous_output = out
                previous_handoff = self._build_handoff_manifest(agent.name, policy_state, out)
            return "\n\n".join(outputs).strip()

        subagent = route.subagent
        if 'subagent_start' in self.callbacks:
            self._emit('subagent_start', name=subagent.name)
        else:
            print(f"\n🧩 当前子Agent：{subagent.name}\n", end="")
        policy = self._get_policy_for_subagent(subagent)
        policy_state = policy.init_state(task)
        if 'stage' in self.callbacks:
            self._emit('stage', stage=policy.stage_label(policy_state))
        else:
            print(f"📍 策略阶段：{policy.stage_label(policy_state)}\n", end="")
        record_changes = subagent.name == "refactor"
        ctx = SubAgentContext(
            run_llm=make_runner(record_changes, policy, policy_state, subagent.name),
            base_messages=base_messages,
            policy_prompt=f"<ui><mode>{'expanded' if self.ui_expanded else 'collapsed'}</mode></ui>\n" + policy.policy_prompt(policy_state),
        )
        step_task = task
        if subagent.name == "explore" and not self.ui_expanded:
            step_task = (
                "请输出短摘要（总计不超过 18 行，每段不超过 5 条要点）。\n"
                "不要写论文式长文；细节以“待补证据清单”列出。\n"
                "如用户需要详细版，提示可用 /expand 或明确要求“详细/展开”。\n\n"
                f"用户需求：{task}"
            )
        return subagent.execute(step_task, ctx)

    def _is_improvement_prep(self, text: str) -> bool:
        t = (text or "")
        return any(k in t for k in ["改进", "重构", "优化", "提升", "refactor", "improve"])

    def _build_handoff_manifest(self, from_agent: str, policy_state: Dict[str, Any], output: str) -> Dict[str, Any]:
        obs = policy_state.get("_observed") or {}
        read_files = list(obs.get("file_read", []))
        read_counts = obs.get("file_read_counts", {})
        shell_count = int(obs.get("shell_command_count") or 0)
        early_stop = bool(policy_state.get("should_stop"))
        stop_reason = policy_state.get("stop_reason")
        manifest = {
            "from_agent": from_agent,
            "read_files": read_files,
            "read_counts": read_counts,
            "shell_command_count": shell_count,
            "early_stop": early_stop,
            "stop_reason": stop_reason,
        }
        logger.info(
            f"HandoffManifest: from={from_agent}, "
            f"files={len(read_files)}, shell={shell_count}, early_stop={early_stop}"
        )
        return manifest

    def _handoff_to_xml(self, handoff: Optional[Dict[str, Any]]) -> str:
        if not handoff:
            return ""
        files = handoff.get("read_files") or []
        counts = handoff.get("read_counts") or {}
        parts = ["<handoff_manifest>"]
        parts.append(f"  <from_agent>{handoff.get('from_agent','')}</from_agent>")
        parts.append("  <read_files>")
        for p in files[:50]:
            c = counts.get(p, 1)
            parts.append(f"    <file path=\"{p}\" count=\"{c}\" />")
        parts.append("  </read_files>")
        parts.append(f"  <early_stop>{'true' if handoff.get('early_stop') else 'false'}</early_stop>")
        if handoff.get("stop_reason"):
            parts.append(f"  <stop_reason>{handoff.get('stop_reason')}</stop_reason>")
        parts.append(f"  <shell_command_count>{int(handoff.get('shell_command_count') or 0)}</shell_command_count>")
        parts.append("</handoff_manifest>")
        return "\n".join(parts)

    def _get_policy_for_subagent(self, subagent: BaseSubAgent) -> SubAgentPolicy:
        name = subagent.name
        if name == "explore":
            return ExplorePolicy()
        if name == "debugger":
            return DebuggerPolicy()
        if name == "reviewer":
            return ReviewerPolicy()
        if name == "test":
            return TestPolicy()
        if name == "refactor":
            return RefactorPolicy()
        if name == "architect":
            return ArchitectPolicy()
        return DefaultPolicy()

    def _build_subagent_base_messages(self, max_messages: int = 12) -> List[Dict[str, Any]]:
        msgs = []
        for m in reversed(self.memory.messages):
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            msg = {k: v for k, v in m.items() if k != "reasoning_content"}
            msgs.append(msg)
            if len(msgs) >= max_messages:
                break
        return list(reversed(msgs))

    def _format_policy_hint_for_terminal(self, hint: str) -> str:
        text = (hint or "").strip()
        if not text:
            return ""
        if "<decision>" in text:
            def _tag(name: str) -> str:
                m = re.search(rf"<{name}>(.*?)</{name}>", text, flags=re.DOTALL | re.IGNORECASE)
                return (m.group(1).strip() if m else "")

            dtype = _tag("type")
            policy = _tag("policy")
            src = _tag("from")
            dst = _tag("to")
            reason = _tag("reason")

            label = "🧠 决策"
            if dtype == "policy_level_upgrade":
                label = "🔺 策略升级"
            elif dtype:
                label = f"🧠 {dtype}"

            parts = []
            if policy:
                parts.append(policy)
            if src or dst:
                parts.append(f"{src or '?'} → {dst or '?'}")
            if reason:
                parts.append(f"原因：{reason}")
            body = "｜".join([p for p in parts if p])
            return f"{label}：{body}".strip()

        if text.startswith(("🛑", "⛔", "✅", "⚠️", "ℹ️")):
            return text
        return f"🧠 策略提示：{text}"

    def _observe_tool_result(self, policy_state: Dict[str, Any], tool_name: str, args: Dict[str, Any]) -> None:
        obs = policy_state.setdefault("_observed", {})
        if tool_name == "file_read":
            path = str(args.get("path", ""))
            if path:
                obs.setdefault("file_read", [])
                obs.setdefault("file_read_counts", {})
                obs["file_read"].append(path)
                obs["file_read_counts"][path] = int(obs["file_read_counts"].get(path, 0)) + 1
        elif tool_name == "shell_command":
            obs["shell_command_count"] = int(obs.get("shell_command_count") or 0) + 1
        elif tool_name == "grep":
            pattern = str(args.get("pattern", ""))
            if pattern:
                obs.setdefault("grep_patterns", []).append(pattern)
        elif tool_name == "glob":
            pattern = str(args.get("pattern", ""))
            if pattern:
                obs.setdefault("glob_patterns", []).append(pattern)
        elif tool_name == "project_structure":
            obs["project_structure_done"] = True
        elif tool_name == "dependency":
            obs["dependency_done"] = True
        elif tool_name == "TodoWrite":
            todos = args.get("todos", [])
            if todos:
                obs.setdefault("todos", [])
                for todo in todos:
                    if isinstance(todo, dict):
                        obs["todos"].append({
                            "id": todo.get("id", ""),
                            "content": todo.get("content", ""),
                            "status": todo.get("status", ""),
                            "priority": todo.get("priority", ""),
                        })
        elif tool_name == "mkdir":
            path = str(args.get("path", ""))
            if path:
                obs.setdefault("created_dirs", []).append(path)
        elif tool_name == "file_delete":
            path = str(args.get("path", ""))
            if path:
                obs.setdefault("deleted_files", []).append(path)
        elif tool_name == "search_replace":
            path = str(args.get("file_path", ""))
            if path:
                obs.setdefault("replaced_files", []).append(path)
                obs["replace_count"] = int(obs.get("replace_count", 0)) + 1

    def _run_subagent_conversation(
        self,
        *,
        system_prompt: str,
        user_input: str,
        permission: ToolPermission,
        enable_thinking: bool,
        thinking_budget: int,
        base_messages: Optional[List[Dict[str, Any]]] = None,
        record_changes: bool = False,
        policy: Optional[SubAgentPolicy] = None,
        policy_state: Optional[Dict[str, Any]] = None,
        subagent_name: str = None,
    ) -> str:
        logger.info(
            f"开始SubAgent会话: thinking={enable_thinking}, "
            f"permission_allowed={permission.allowed_tools}, "
            f"permission_restricted={permission.restricted_tools}"
        )
        temp_memory = Memory()
        temp_memory.set_system_prompt(system_prompt)
        temp_memory.knowledge = self.memory.knowledge.copy()
        if base_messages:
            temp_memory.messages.extend([{k: v for k, v in m.items() if k != "reasoning_content"} for m in base_messages])
        temp_memory.add_user_message(user_input)

        old_permission = getattr(self.executor, "_permission", None)
        try:
            max_iters = 20
            local_input_tokens = 0
            local_output_tokens = 0
            for _ in range(max_iters):
                effective_permission = permission
                if policy and policy_state is not None:
                    effective_permission = policy.effective_permission(permission, policy_state)
                self.executor.set_permission(effective_permission)
                messages = temp_memory.build_context(task_type=subagent_name)
                tools = self.executor.get_tool_definitions()

                stream_handler = StreamHandler(
                    on_reasoning=self._on_reasoning,
                    on_content=self._on_content,
                    on_tool_call=lambda _: None,
                )

                stream = self.llm.stream_completion(
                    messages=messages,
                    tools=tools if tools else None,
                    enable_thinking=enable_thinking,
                    thinking_budget=thinking_budget,
                )

                for chunk in stream:
                    stream_handler.process_chunk(chunk)

                state = stream_handler.finalize()
                self.reasoning_handler.end_reasoning_block()
                
                if state.input_tokens == 0:
                    state.input_tokens = temp_memory.get_token_count()
                
                self.input_tokens_used += state.input_tokens
                self.output_tokens_used += state.output_tokens
                local_input_tokens += state.input_tokens
                local_output_tokens += state.output_tokens
                self._last_input_tokens = state.input_tokens
                self._last_output_tokens = state.output_tokens

                tool_calls = state.tool_calls
                content = state.content
                reasoning = state.reasoning_content

                if tool_calls:
                    refused_results: List[Dict[str, Any]] = []
                    allowed_calls: List[Dict[str, Any]] = []

                    for tc in tool_calls:
                        tool_name = tc.get("function", {}).get("name", "unknown")
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except Exception:
                            args = {}

                        if policy and policy_state is not None:
                            decision = policy.validate_tool_call(tool_name, args, policy_state)
                            if not decision.allowed:
                                blocked = f"⛔ 已阻止，未执行：{tool_name}({', '.join([f'{k}={repr(v)}' for k, v in args.items() if k in {'path','file_path','pattern','command'}])})"
                                if decision.reason:
                                    blocked = f"{blocked}｜原因：{decision.reason}"
                                if 'policy_event' in self.callbacks:
                                    self._emit('policy_event', text=blocked)
                                elif 'tool_result' in self.callbacks:
                                    self._emit('tool_result', tool_name="policy_reject", result=blocked, args={})
                                else:
                                    logger.info(blocked)
                                refused_results.append(
                                    {
                                        "tool_call_id": tc.get("id", ""),
                                        "content": decision.reason or "策略拒绝：该工具调用不符合当前策略。",
                                    }
                                )
                                continue

                        if 'tool_call' in self.callbacks:
                            self._emit('tool_call', tool_name=tool_name, args=args)
                        logger.info(f"[SubAgent] 工具调用: {tool_name}({', '.join([f'{k}={repr(v)[:50]}' for k, v in args.items() if k in {'path','file_path','pattern','command','query'}])})")
                        allowed_calls.append(tc)

                    assistant_msg = {"role": "assistant", "tool_calls": self._format_tool_calls_for_memory(tool_calls)}
                    if content and content.strip():
                        assistant_msg["content"] = content
                    if reasoning and reasoning.strip():
                        assistant_msg["reasoning_content"] = reasoning
                    temp_memory.messages.append(assistant_msg)

                    for rr in refused_results:
                        if rr.get("tool_call_id"):
                            temp_memory.add_tool_result(
                                tool_call_id=rr["tool_call_id"],
                                content=rr["content"],
                            )

                    if not allowed_calls:
                        continue

                    results = self._execute_tool_calls_with_optional_history(allowed_calls, record_changes)
                    for result in results:
                        tool_name = "unknown"
                        args = {}
                        for tc in allowed_calls:
                            if tc.get("id") == result.get("tool_call_id"):
                                tool_name = tc.get("function", {}).get("name", "unknown")
                                args_str = tc.get("function", {}).get("arguments", "{}")
                                try:
                                    args = json.loads(args_str) if args_str else {}
                                except Exception:
                                    args = {}
                                break
                        if 'tool_result' in self.callbacks:
                            self._emit('tool_result', tool_name=tool_name, result=result.get("content", ""), args=args)
                        result_preview = result.get("content", "")[:200] if result.get("content") else "(空)"
                        logger.info(f"[SubAgent] 工具结果: {tool_name} → {result_preview.replace(chr(10), ' ')[:100]}...")
                        if policy_state is not None:
                            self._observe_tool_result(policy_state, tool_name, args)
                        if policy and policy_state is not None:
                            hint = policy.on_tool_result(tool_name, args, result.get("content", ""), policy_state)
                            if hint:
                                logger.info(f"PolicyHint: {hint}")
                                if 'policy_event' in self.callbacks:
                                    self._emit('policy_event', text=hint)
                                else:
                                    pretty = self._format_policy_hint_for_terminal(hint)
                                    print(f"\n{pretty}\n", end="")
                        temp_memory.add_tool_result(
                            tool_call_id=result["tool_call_id"],
                            content=result["content"],
                        )
                    continue

                if content and content.strip():
                    print()
                    self._last_input_tokens = local_input_tokens
                    self._last_output_tokens = local_output_tokens
                    
                    observed = policy_state.get("_observed", {}) if policy_state else {}
                    files_read = observed.get("file_read", [])
                    if files_read:
                        self.memory.add_knowledge("subagent.files_read", list(set(files_read)))
                    
                    todos = observed.get("todos", [])
                    if todos:
                        self.memory.add_knowledge("subagent.todos", todos)
                    
                    created_dirs = observed.get("created_dirs", [])
                    if created_dirs:
                        self.memory.add_knowledge("subagent.created_dirs", list(set(created_dirs)))
                    
                    deleted_files = observed.get("deleted_files", [])
                    if deleted_files:
                        self.memory.add_knowledge("subagent.deleted_files", list(set(deleted_files)))
                    
                    replaced_files = observed.get("replaced_files", [])
                    if replaced_files:
                        self.memory.add_knowledge("subagent.replaced_files", list(set(replaced_files)))
                    
                    replace_count = observed.get("replace_count", 0)
                    if replace_count > 0:
                        self.memory.add_knowledge("subagent.replace_count", replace_count)
                    
                    grep_patterns = observed.get("grep_patterns", [])
                    if grep_patterns:
                        self.memory.add_knowledge("subagent.grep_patterns", list(set(grep_patterns)))
                    
                    glob_patterns = observed.get("glob_patterns", [])
                    if glob_patterns:
                        self.memory.add_knowledge("subagent.glob_patterns", list(set(glob_patterns)))
                    
                    logger.info(
                        f"结束SubAgent会话: input_tokens={local_input_tokens}, "
                        f"output_tokens={local_output_tokens}, "
                        f"files_read={len(files_read)}, "
                        f"todos={len(todos)}, "
                        f"created_dirs={len(created_dirs)}, "
                        f"deleted_files={len(deleted_files)}, "
                        f"replaced_files={len(replaced_files)}"
                    )
                    return content

            self._last_input_tokens = local_input_tokens
            self._last_output_tokens = local_output_tokens
            return "任务执行未在安全迭代内完成。"
        finally:
            self.executor.set_permission(old_permission)

    def _execute_tool_calls_with_optional_history(
        self,
        tool_calls: List[Dict[str, Any]],
        record_changes: bool,
    ) -> List[Dict[str, Any]]:
        if not record_changes:
            return self.executor.execute(tool_calls)

        results: List[Dict[str, Any]] = []
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(args_str) if args_str else {}
            except Exception:
                args = {}

            before = None
            resolved_path = None
            if tool_name in ("file_write", "search_replace"):
                p = args.get("path")
                if isinstance(p, str) and p:
                    resolved_path = self._resolve_work_path(p)
                    if resolved_path.exists() and resolved_path.is_file():
                        try:
                            before = resolved_path.read_text(encoding="utf-8")
                        except Exception:
                            before = None

            r = self.executor.execute([tc])[0]

            if resolved_path is not None and tool_name in ("file_write", "search_replace"):
                after = None
                if resolved_path.exists() and resolved_path.is_file():
                    try:
                        after = resolved_path.read_text(encoding="utf-8")
                    except Exception:
                        after = None
                self.change_history.record(
                    change_type="modify",
                    file_path=str(resolved_path),
                    old_content=before,
                    new_content=after,
                )
            results.append(r)
        return results

    def _resolve_work_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p.resolve()
        return (get_work_dir() / p).resolve()
    
    def _process_conversation(self) -> str:
        self.followup_state.iteration_count = 0
        
        while self.followup_state.iteration_count < self.followup_state.max_safe_iterations:
            self.followup_state.iteration_count += 1
            
            messages = self.memory.build_context(task_type="main")
            tools = self.executor.get_tool_definitions()
            
            if DEBUG:
                logger.debug(f">>> 发送的 messages: {json.dumps(messages, indent=2, ensure_ascii=False)}")
                if tools:
                    logger.debug(f">>> 发送的 tools 数量: {len(tools)}")
            
            stream_handler = StreamHandler(
                on_reasoning=self._on_reasoning,
                on_content=self._on_content,
            )
            
            try:
                stream = self.llm.stream_completion(
                    messages=messages,
                    tools=tools if tools else None,
                    enable_thinking=self.enable_thinking,
                    thinking_budget=self.thinking_budget,
                )
                
                for chunk in stream:
                    stream_handler.process_chunk(chunk)
                
                state = stream_handler.finalize()
                
                self.input_tokens_used += state.input_tokens
                self.output_tokens_used += state.output_tokens
                
            except Exception as e:
                logger.error(f"LLM 调用失败: {str(e)}")
                return f"抱歉，处理请求时发生错误: {str(e)}"
            
            self.reasoning_handler.end_reasoning_block()
            
            tool_calls = state.tool_calls
            content = state.content
            reasoning = state.reasoning_content
            
            if not tool_calls and not content and not reasoning:
                logger.warning("收到空响应，尝试重试")
                self.followup_state.iteration_count += 1
                if self.followup_state.iteration_count < 3:
                    self.memory.add_assistant_message(content="我收到了一个空响应，正在重新处理您的请求...")
                    print(f"\n\033[33m⚠️ 收到空响应，正在重试 ({self.followup_state.iteration_count}/3)...\033[0m")
                    continue
                else:
                    return "抱歉，我多次尝试处理您的请求但收到了空响应。请尝试重新描述您的需求或切换到其他模型。"
            
            self.followup_state.iteration_count = 0
            
            if tool_calls and len(tool_calls) > 0:
                valid_tool_calls = []
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    tc_func = tc.get("function", {})
                    tc_name = tc_func.get("name", "")
                    tc_args = tc_func.get("arguments", "")
                    
                    if tc_name and tc_id:
                        valid_tool_calls.append(tc)
                    else:
                        logger.warning(f"跳过无效的工具调用: id={tc_id}, name={tc_name}")
                
                if not valid_tool_calls:
                    logger.warning("没有有效的工具调用，跳过执行")
                    self.memory.add_assistant_message(content=content or "我需要调用工具来完成任务，但工具调用格式不正确。请让我重新尝试。")
                    continue
                
                tool_calls = valid_tool_calls
                is_parallel = len(tool_calls) > 1
                if is_parallel:
                    if 'parallel_start' in self.callbacks:
                        self._emit('parallel_start', count=len(tool_calls))
                    else:
                        print(f"\n\033[33m🔧 并行执行 {len(tool_calls)} 个工具...\033[0m")
                else:
                    if 'parallel_start' in self.callbacks:
                        self._emit('parallel_start', count=1)
                    else:
                        print(f"\n\033[33m🔧 执行工具调用...\033[0m")
                
                formatted_tool_calls = self._format_tool_calls_for_memory(tool_calls)
                
                assistant_msg = {"role": "assistant", "tool_calls": formatted_tool_calls}
                if content and content.strip():
                    assistant_msg["content"] = content
                if reasoning and reasoning.strip():
                    assistant_msg["reasoning_content"] = reasoning
                self.memory.messages.append(assistant_msg)
                
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except:
                        args = {}
                    if 'tool_call' in self.callbacks:
                        self._emit('tool_call', tool_name=tool_name, args=args)
                    else:
                        print(f"\033[33m  📌 {tool_name}\033[0m")
                        if args:
                            print(f"\033[90m     参数: {json.dumps(args, ensure_ascii=False)}\033[0m")
                
                results = self.executor.execute(tool_calls)
                
                success_count = 0
                for result in results:
                    result_content = result['content']
                    if not result_content.startswith("工具") or "失败" not in result_content:
                        success_count += 1
                    tool_name = "unknown"
                    for tc in tool_calls:
                        if tc.get("id") == result["tool_call_id"]:
                            tool_name = tc.get("function", {}).get("name", "unknown")
                            break
                    args_str = "{}"
                    for tc in tool_calls:
                        if tc.get("id") == result["tool_call_id"]:
                            args_str = tc.get("function", {}).get("arguments", "{}")
                            break
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except:
                        args = {}
                    if 'tool_result' in self.callbacks:
                        self._emit('tool_result', tool_name=tool_name, result=result['content'], args=args)
                    else:
                        display_content = result_content
                        if len(display_content) > 300:
                            display_content = display_content[:300] + "..."
                        print(f"\033[36m  ✅ 结果: {display_content}\033[0m")
                    self.memory.add_tool_result(
                        tool_call_id=result["tool_call_id"],
                        content=result["content"]
                    )
                
                if is_parallel:
                    if 'parallel_complete' in self.callbacks:
                        self._emit('parallel_complete', success=success_count, total=len(tool_calls))
                    else:
                        print(f"\033[33m  📊 并行执行完成: {success_count}/{len(tool_calls)} 成功\033[0m")
                
                continue
            
            if content:
                self.memory.add_assistant_message(content=content)
                print()
                
                self._log_interaction(
                    user_input=self.memory.get_last_user_message(),
                    response=content,
                    reasoning=reasoning,
                    tool_calls=None
                )
                
                task_state = self._detect_task_state(content, reasoning)
                if task_state == TaskState.COMPLETED:
                    self.followup_state.pending = False
                    return content
                elif task_state == TaskState.NEEDS_INPUT:
                    self.followup_state.pending = False
                    return content
                else:
                    self.followup_state.pending = True
                    self.followup_state.reason = "任务需要继续执行"
                    return content
            
            return "抱歉，我无法生成有效的回复。"
        
        logger.warning(f"达到安全迭代上限: {self.followup_state.max_safe_iterations}")
        self.followup_state.pending = True
        self.followup_state.reason = "任务执行时间较长，已暂停"
        return "任务执行时间较长，已暂停。输入 /continue 继续执行。"
    
    def _emit(self, event: str, **kwargs) -> None:
        """触发事件回调"""
        callback = self.callbacks.get(event)
        if callback:
            callback(**kwargs)
    
    def _on_reasoning(self, chunk: str) -> None:
        self.reasoning_handler.handle_chunk(chunk)
    
    def _on_content(self, chunk: str) -> None:
        if 'content' in self.callbacks:
            self._emit('content', chunk=chunk)
        else:
            print(f"\033[32m{chunk}\033[0m", end="", flush=True)
    
    def _detect_task_state(self, content: str, reasoning: Optional[str] = None) -> TaskState:
        """
        检测任务状态
        
        Args:
            content: 模型输出的内容
            reasoning: 思考模式下的推理内容
            
        Returns:
            TaskState 枚举值
        """
        if not content:
            return TaskState.CONTINUE
        
        content_lower = content.lower()
        
        completion_signals = [
            "任务完成", "已完成", "全部完成", "所有步骤已完成",
            "done", "completed", "finished", "all done"
        ]
        for signal in completion_signals:
            if signal in content_lower:
                return TaskState.COMPLETED
        
        input_signals = [
            "请确认", "请选择", "需要您", "请问您",
            "please confirm", "please select", "need your"
        ]
        for signal in input_signals:
            if signal in content_lower:
                return TaskState.NEEDS_INPUT
        
        if reasoning and self.enable_thinking:
            if "所有计划步骤已完成" in reasoning:
                return TaskState.COMPLETED
            if "还需要执行" in reasoning or "下一步" in reasoning:
                return TaskState.CONTINUE
        
        return TaskState.COMPLETED
    
    def _format_tool_calls_for_memory(self, tool_calls: List[Dict]) -> List[Dict]:
        formatted = []
        for tc in tool_calls:
            args = tc.get("function", {}).get("arguments", "")
            if not args:
                args = "{}"
            formatted.append({
                "id": tc.get("id", ""),
                "type": tc.get("type", "function"),
                "function": {
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": args
                }
            })
        return formatted
    
    def _log_interaction(
        self,
        user_input: Optional[str],
        response: str,
        reasoning: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None
    ) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user": user_input,
            "assistant": response,
        }
        if reasoning:
            entry["reasoning"] = reasoning
        if tool_calls:
            entry["tool_calls"] = tool_calls
        
        self.conversation_log.append(entry)
    
    def save_conversation(self) -> str:
        sessions_dir = get_sessions_dir()
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{timestamp}.json"
        filepath = sessions_dir / filename
        
        data = {
            "session_start": self.session_start_time.isoformat(),
            "session_end": datetime.now().isoformat(),
            "work_dir": str(get_work_dir()),
            "messages": self.memory.messages,
            "conversation_log": self.conversation_log,
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"对话已保存: {filepath}")
        return str(filepath)
    
    def clear_memory(self) -> None:
        self.memory.clear()
        self.reasoning_handler.reset()
        self.conversation_log = []
        self.session_start_time = datetime.now()
        logger.info("对话记忆已清除")
    
    def get_conversation_summary(self) -> str:
        return self.memory.get_conversation_summary()
    
    def set_thinking_mode(self, enabled: bool) -> None:
        self.enable_thinking = enabled
        status = "开启" if enabled else "关闭"
        logger.info(f"思考模式已{status}")
    
    def is_thinking_enabled(self) -> bool:
        return self.enable_thinking
    
    def analyze_project(self) -> str:
        """分析项目结构"""
        from tools import ProjectStructureTool
        tool = ProjectStructureTool()
        return tool.execute(path=str(get_work_dir()))
    
    def get_history(self, n: int = 10) -> str:
        """获取变更历史"""
        changes = self.change_history.get_recent(n)
        if not changes:
            return "暂无变更历史"
        
        result = []
        for i, change in enumerate(changes, 1):
            result.append(f"{i}. [{change['timestamp']}] {change['file_path']}")
            if change.get('change_type'):
                result.append(f"   类型: {change['change_type']}")
        
        undo_count = self.change_history.get_undo_count()
        redo_count = self.change_history.get_redo_count()
        result.append(f"\n可撤销: {undo_count} 步 | 可重做: {redo_count} 步")
        
        return "\n".join(result)
    
    def undo_last_change(self) -> str:
        """撤销最近一次变更"""
        record = self.change_history.undo()
        if not record:
            return "没有可撤销的变更"
        
        file_path = record.file_path
        old_content = record.old_content
        change_type = record.change_type
        
        try:
            if change_type == "create":
                from pathlib import Path
                Path(file_path).unlink(missing_ok=True)
                return f"已撤销创建: {file_path}"
            elif change_type == "delete":
                from pathlib import Path
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(old_content or "")
                return f"已撤销删除: {file_path}"
            else:
                if old_content is None:
                    return f"无法撤销: {file_path} (缺少旧内容)"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(old_content)
                return f"已撤销修改: {file_path}"
        except Exception as e:
            return f"撤销失败: {str(e)}"
    
    def redo_last_change(self) -> str:
        """重做最近一次撤销的变更"""
        record = self.change_history.redo()
        if not record:
            return "没有可重做的变更"
        
        file_path = record.file_path
        new_content = record.new_content
        change_type = record.change_type
        
        try:
            if change_type == "create":
                from pathlib import Path
                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content or "")
                return f"已重做创建: {file_path}"
            elif change_type == "delete":
                from pathlib import Path
                Path(file_path).unlink(missing_ok=True)
                return f"已重做删除: {file_path}"
            else:
                if new_content is None:
                    return f"无法重做: {file_path} (缺少新内容)"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return f"已重做修改: {file_path}"
        except Exception as e:
            return f"重做失败: {str(e)}"
    
    def can_undo(self) -> bool:
        """检查是否可以撤销"""
        return self.change_history.can_undo()
    
    def can_redo(self) -> bool:
        """检查是否可以重做"""
        return self.change_history.can_redo()
    
    def _generate_followup_prompt(self) -> str:
        """生成续行提示"""
        if self.followup_state.remaining_tasks:
            tasks = "\n".join(f"- {t}" for t in self.followup_state.remaining_tasks)
            return f"请继续执行以下任务:\n{tasks}"
        return "请继续之前的任务。"
    
    def has_pending_followup(self) -> bool:
        """检查是否有待处理的续行任务"""
        return self.followup_state.pending
    
    def get_followup_status(self) -> str:
        """获取续行状态"""
        if not self.followup_state.pending:
            return "当前没有待处理的任务"
        
        status = f"迭代次数: {self.followup_state.iteration_count}/{self.followup_state.max_safe_iterations}"
        if self.followup_state.reason:
            status += f"\n原因: {self.followup_state.reason}"
        if self.followup_state.remaining_tasks:
            status += f"\n剩余任务: {len(self.followup_state.remaining_tasks)} 项"
        return status
    
    def continue_task(self) -> str:
        """继续执行暂停的任务"""
        if not self.followup_state.pending:
            return "没有待继续的任务"
        
        prompt = self._generate_followup_prompt()
        self.memory.add_user_message(prompt)
        return self._process_conversation()
    
    def stop_task(self) -> None:
        """停止当前任务"""
        self.followup_state.pending = False
        self.followup_state.remaining_tasks = []
        self.followup_state.reason = ""
        logger.info("任务已停止")
    
    def save_session(self) -> str:
        """保存当前会话到工作区"""
        work_dir = get_work_dir()
        session_dir = work_dir / ".agent_data" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        latest_path = session_dir / "latest.json"
        
        self.memory.save_to_file(latest_path)
        
        data = {
            "session_start": self.session_start_time.isoformat(),
            "session_end": datetime.now().isoformat(),
            "work_dir": str(work_dir),
            "conversation_log": self.conversation_log,
            "followup_state": {
                "pending": self.followup_state.pending,
                "reason": self.followup_state.reason,
                "remaining_tasks": self.followup_state.remaining_tasks,
            }
        }
        
        with open(latest_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        
        existing.update(data)
        
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        backup_path = session_dir / f"session_{timestamp}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        logger.info(f"会话已保存: {latest_path}")
        return str(latest_path)
    
    def load_session(self, filepath: str = None) -> bool:
        """加载会话"""
        if filepath:
            path = Path(filepath)
        else:
            work_dir = get_work_dir()
            path = work_dir / ".agent_data" / "sessions" / "latest.json"
        
        if not path.exists():
            return False
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.memory.load_from_file(path)
            
            self.conversation_log = data.get("conversation_log", [])
            
            followup = data.get("followup_state", {})
            self.followup_state.pending = followup.get("pending", False)
            self.followup_state.reason = followup.get("reason", "")
            self.followup_state.remaining_tasks = followup.get("remaining_tasks", [])
            
            if "session_start" in data:
                self.session_start_time = datetime.fromisoformat(data["session_start"])
            
            logger.info(f"会话已加载: {path}")
            return True
        except Exception as e:
            logger.error(f"加载会话失败: {str(e)}")
            return False
    
    def has_previous_session(self) -> bool:
        """检查是否有历史会话"""
        work_dir = get_work_dir()
        latest_path = work_dir / ".agent_data" / "sessions" / "latest.json"
        return latest_path.exists()
    
    def get_session_info(self) -> Optional[Dict]:
        """获取会话信息"""
        work_dir = get_work_dir()
        latest_path = work_dir / ".agent_data" / "sessions" / "latest.json"
        
        if not latest_path.exists():
            return None
        
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return {
                "session_start": data.get("session_start"),
                "session_end": data.get("session_end"),
                "message_count": len(data.get("messages", [])),
                "has_knowledge": bool(data.get("knowledge")),
            }
        except Exception:
            return None
    
    def _save_history_backup(self) -> str:
        work_dir = get_work_dir()
        history_dir = work_dir / ".agent_data" / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = history_dir / f"history_{timestamp}.json"
        
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "messages": self.memory.messages,
                "compressed_summary": self.memory.compressed_summary
            }, f, ensure_ascii=False, indent=2)
        
        return str(backup_file)
    
    def compress_context(self) -> str:
        if len(self.memory.messages) < 10:
            return "上下文较短，无需压缩"
        
        keep_recent = 6
        messages_to_compress = self.memory.messages[:-keep_recent]
        recent_messages = self.memory.messages[-keep_recent:]
        
        if not messages_to_compress:
            return "没有可压缩的内容"
        
        self.memory.extract_and_store_knowledge(messages_to_compress)
        
        backup_path = self._save_history_backup()
        
        summary_prompt = """请将以下对话历史压缩为简洁的摘要，保留关键信息：
1. 用户的主要请求和目标
2. 已完成的主要操作
3. 创建或修改的重要文件
4. 重要的决策或结论

对话历史：
""" + "\n".join([
            f"{m.get('role')}: {str(m.get('content', ''))[:200]}"
            for m in messages_to_compress[:20]
        ])
        
        try:
            messages = [
                {"role": "system", "content": "你是一个对话摘要助手，请简洁地总结对话内容。"},
                {"role": "user", "content": summary_prompt}
            ]
            
            stream = self.llm.stream_completion(
                messages=messages,
                tools=None,
                enable_thinking=False,
            )
            
            summary = ""
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    summary += chunk.choices[0].delta.content
            
            self.memory.compressed_summary = summary
            self.memory.messages = recent_messages
            self.memory.add_knowledge("history_backup", backup_path)
            
            logger.info(f"上下文已压缩，保留最近 {keep_recent} 条消息")
            return f"上下文已压缩。摘要：\n{summary[:200]}...\n\n[完整历史已保存至: {backup_path}]"
            
        except Exception as e:
            logger.error(f"LLM 压缩失败，降级到简单截断策略: {str(e)}")
            
            self.memory.compressed_summary = "[上下文已压缩（降级模式），部分历史已丢弃]"
            self.memory.messages = recent_messages
            self.memory.add_knowledge("history_backup", backup_path)
            
            return f"[压缩失败，已降级处理。完整历史已保存至: {backup_path}]"
    
    def check_and_compress(self) -> Optional[str]:
        """检查并自动压缩上下文"""
        if self.memory.needs_compression():
            print(f"\n\033[33m📦 上下文已达到 {self.memory.get_context_usage_percent()*100:.1f}%，正在自动压缩...\033[0m")
            return self.compress_context()
        return None
