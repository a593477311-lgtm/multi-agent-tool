from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional, Tuple, List

from .subagents.base import ToolPermission


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""
    stage_hint: Optional[str] = None


class SubAgentPolicy:
    name: str = "default"

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return {"user_input": user_input}

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return ""

    def stage_label(self, state: Dict[str, Any]) -> str:
        return self.name

    def effective_permission(self, base: ToolPermission, state: Dict[str, Any]) -> ToolPermission:
        return base

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        return PolicyDecision(allowed=True)

    def on_tool_result(self, tool_name: str, args: Dict[str, Any], result: str, state: Dict[str, Any]) -> Optional[str]:
        return None


class DefaultPolicy(SubAgentPolicy):
    name = "default"

    def init_state(self, user_input: str) -> Dict[str, Any]:
        text = user_input or ""
        allow_wide = any(k in text for k in ["全量", "全面", "全局", "所有文件", "全仓库", "whole repo", "entire repo"])
        return {"user_input": user_input, "allow_wide_scan": allow_wide}

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        if state.get("allow_wide_scan"):
            return PolicyDecision(allowed=True)

        if tool_name == "glob":
            pattern = str(args.get("pattern", ""))
            if pattern.strip() == "**/*":
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：默认不允许全局 glob '**/*'。请先限定目录或文件类型，或明确要求“全量/全局”。",
                )

        if tool_name == "symbol":
            path = str(args.get("path", ""))
            if path in {"", ".", "./"}:
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：默认不允许 symbol('.') 全仓库扫描。请先限定目录/文件，或明确要求“全量/全局”。",
                )

        return PolicyDecision(allowed=True)


class ExplorePolicy(SubAgentPolicy):
    name = "explore"

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return {
            "user_input": user_input,
            "level": "L1",
            "stats": None,
            "project_types": None,
            "upgrade_reason": None,
            "project_structure_done": False,
            "file_read_count": 0,
            "should_stop": False,
            "stop_reason": None,
        }

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>渐进式探索：L1(轻量) → L2(标准) → L3(深入)</goal>\n"
            "      <goal>优先用最少工具得到足够信息；信息足够就停止继续扫描并输出总结</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"L1\">project_structure → 读取 1 个代表入口/关键文件 → 总结</phase>\n"
            "      <phase id=\"L2\">仅当入口不明确/结构中等时升级；允许定向 grep/glob 与额外读取 1 个关键文件</phase>\n"
            "      <phase id=\"L3\">仅当大项目/高依赖/多入口或用户明确要求全面分析时升级；允许 dependency/symbol</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>默认避免无边界扫描（glob '**/*'、symbol('.')、过宽 grep）；确有必要且策略允许时再用</guard>\n"
            "      <guard>早停：已明确“项目类型 + 入口/运行方式 + 关键模块 + 典型调用链”就停止工具调用并输出</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>项目概览</section>\n"
            "      <section>关键入口</section>\n"
            "      <section>调用链</section>\n"
            "      <section>风险与建议</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def stage_label(self, state: Dict[str, Any]) -> str:
        level = state.get("level", "L1")
        return f"Explore:{level}"

    def effective_permission(self, base: ToolPermission, state: Dict[str, Any]) -> ToolPermission:
        level = state.get("level", "L1")
        allowed_by_level = {
            "L1": {"project_structure", "file_read", "list_dir"},
            "L2": {"project_structure", "file_read", "list_dir", "grep", "glob"},
            "L3": {"project_structure", "file_read", "list_dir", "grep", "glob", "dependency", "symbol"},
        }
        allowed = set(base.allowed_tools or [])
        level_allowed = allowed_by_level.get(level, allowed)
        always_allowed = {"TodoWrite"}
        allowed = allowed.intersection(level_allowed).union(always_allowed)
        restricted = set(base.restricted_tools or [])
        return ToolPermission(allowed_tools=sorted(allowed), restricted_tools=sorted(restricted))

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        level = state.get("level", "L1")

        if state.get("should_stop"):
            return PolicyDecision(
                allowed=False,
                reason=f"🛑 策略早停：{state.get('stop_reason') or '信息已足够'}。请停止继续调用工具，直接输出结构化总结。",
            )

        if level == "L1":
            if tool_name in {"dependency", "symbol"}:
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：当前为 L1(轻量) 探索，禁止使用 dependency/symbol。请先用 project_structure 与少量 file_read 确定入口与模块。",
                )
            if tool_name == "glob":
                pattern = str(args.get("pattern", ""))
                if pattern.strip() == "**/*":
                    return PolicyDecision(
                        allowed=False,
                        reason="⛔ 策略拒绝：L1 不允许全局 glob '**/*'。请先依赖 project_structure 的树与配置文件线索。",
                    )
            if tool_name == "grep":
                pattern = str(args.get("pattern", ""))
                if len(pattern.strip()) < 4:
                    return PolicyDecision(
                        allowed=False,
                        reason="⛔ 策略拒绝：L1 不允许过宽的 grep。请提供更具体的入口/框架关键词。",
                    )

        if tool_name == "symbol":
            path = str(args.get("path", ""))
            if path in {"", ".", "./"} and level != "L3":
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：symbol('.') 属于宽范围扫描，仅允许在 L3(深入) 使用。",
                )

        if tool_name == "glob":
            pattern = str(args.get("pattern", ""))
            if pattern.strip() == "**/*" and level != "L3":
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：全局 glob '**/*' 仅允许在 L3(深入) 使用。",
                )

        return PolicyDecision(allowed=True)

    def on_tool_result(self, tool_name: str, args: Dict[str, Any], result: str, state: Dict[str, Any]) -> Optional[str]:
        if tool_name == "project_structure":
            stats = self._parse_project_structure_stats(result)
            types = self._parse_project_types(result)
            state["stats"] = stats
            state["project_types"] = types
            state["project_structure_done"] = True
            level, reason = self._decide_level(stats, types, state.get("user_input", ""))
            if level != state.get("level"):
                previous = state.get("level")
                state["level"] = level
                state["upgrade_reason"] = reason
                return (
                    "<decision>\n"
                    f"  <type>policy_level_upgrade</type>\n"
                    f"  <policy>{self.name}</policy>\n"
                    f"  <from>{previous}</from>\n"
                    f"  <to>{level}</to>\n"
                    f"  <reason>{reason}</reason>\n"
                    "</decision>\n"
                )
        if tool_name == "file_read":
            state["file_read_count"] = int(state.get("file_read_count") or 0) + 1
            if self._is_information_sufficient(state, last_file_content=result):
                state["should_stop"] = True
                state["stop_reason"] = "已获取项目结构与代表性入口/关键文件"
        return None

    def _is_information_sufficient(self, state: Dict[str, Any], last_file_content: str) -> bool:
        level = state.get("level", "L1")
        stats = state.get("stats") or {}
        total_files = int(stats.get("total_files") or 0)
        if level != "L1":
            return False
        if not state.get("project_structure_done"):
            return False
        if total_files > 15:
            return False
        if int(state.get("file_read_count") or 0) < 1:
            return False
        content = last_file_content or ""
        if "__name__" in content and "main(" in content:
            return True
        return True

    def _parse_project_structure_stats(self, text: str) -> Dict[str, Any]:
        total_dirs = self._find_int(text, r"目录数量:\s*(\d+)")
        total_files = self._find_int(text, r"文件数量:\s*(\d+)")
        return {
            "total_dirs": total_dirs,
            "total_files": total_files,
        }

    def _parse_project_types(self, text: str) -> List[str]:
        m = re.search(r"📋 项目类型:\s*(.+)", text)
        if not m:
            return []
        types = [t.strip() for t in m.group(1).split(",") if t.strip()]
        return types

    def _decide_level(self, stats: Dict[str, Any], types: List[str], user_input: str) -> Tuple[str, str]:
        total_files = int(stats.get("total_files") or 0)
        total_dirs = int(stats.get("total_dirs") or 0)
        wants_deep = any(k in (user_input or "") for k in ["依赖", "全量", "全面", "全局", "所有文件", "调用图", "符号"])

        if wants_deep:
            if total_files >= 120 or total_dirs >= 40:
                return "L3", "用户要求全面分析且项目较大"
            return "L2", "用户要求更深入分析"

        if total_files >= 200 or total_dirs >= 60:
            return "L3", "项目规模较大"

        if total_files >= 60 or total_dirs >= 25:
            return "L2", "项目规模中等或入口不一定明确"

        if any("Node.js" in t for t in types) and total_files >= 40:
            return "L2", "多语言/Node 项目倾向更复杂"

        return "L1", "项目规模较小"

    def _find_int(self, text: str, pattern: str) -> int:
        m = re.search(pattern, text)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except Exception:
            return 0


class ReviewerPolicy(SubAgentPolicy):
    name = "reviewer"

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>先锁定目标文件/模块，再审查；默认避免全仓库扫描</goal>\n"
            "      <goal>输出按高/中/低风险分级，给出可操作建议</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"1\">锁定范围（用户指定优先；否则先用结构工具找入口/关键模块）</phase>\n"
            "      <phase id=\"2\">阅读证据（聚焦关键文件与相关调用点）</phase>\n"
            "      <phase id=\"3\">风险分级（高/中/低）并给出可操作建议</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>只读：不执行写入/删除/命令</guard>\n"
            "      <guard>除非用户明确要求“全量/全局/全仓库”，否则禁止宽范围扫描</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>结论摘要（高/中/低风险）</section>\n"
            "      <section>关键问题清单（含位置与原因）</section>\n"
            "      <section>建议修改方向（不直接修改代码）</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return DefaultPolicy().init_state(user_input)

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        return DefaultPolicy().validate_tool_call(tool_name, args, state)


class DebuggerPolicy(SubAgentPolicy):
    name = "debugger"

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>修复闭环：复现/定位 → 根因 → 最小修改 → 验证</goal>\n"
            "      <goal>避免无关改动，优先最小范围定位</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"1\">复现/定位（先证据后假设）</phase>\n"
            "      <phase id=\"2\">根因分析（触发条件 + 代码路径）</phase>\n"
            "      <phase id=\"3\">最小修复（避免无关重构）</phase>\n"
            "      <phase id=\"4\">验证（优先运行现有测试）</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>在修改前先读相关文件并定位最小范围</guard>\n"
            "      <guard>默认避免全仓库宽扫描，除非用户明确要求“全量/全局/全仓库”</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>现象与复现</section>\n"
            "      <section>根因</section>\n"
            "      <section>修复（最小变更）</section>\n"
            "      <section>验证步骤</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return DefaultPolicy().init_state(user_input)

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        return DefaultPolicy().validate_tool_call(tool_name, args, state)


class TestPolicy(SubAgentPolicy):
    name = "test"

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>默认使用 unittest；新增测试必须可运行</goal>\n"
            "      <goal>覆盖核心/边界/异常路径；尽量执行 python -m unittest</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"1\">定位被测对象（文件/函数/行为）</phase>\n"
            "      <phase id=\"2\">编写测试（核心/边界/异常）</phase>\n"
            "      <phase id=\"3\">运行验证（优先 python -m unittest）</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>优先先读被测代码，再写测试</guard>\n"
            "      <guard>默认避免全仓库宽扫描，除非用户明确要求“全量/全局/全仓库”</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>测试策略</section>\n"
            "      <section>新增/修改的测试文件</section>\n"
            "      <section>运行命令与结果</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return DefaultPolicy().init_state(user_input)

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        return DefaultPolicy().validate_tool_call(tool_name, args, state)


class RefactorPolicy(SubAgentPolicy):
    name = "refactor"

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>小步重构：每步可验证/可回滚，保持行为不变</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"1\">识别异味与目标（基于证据）</phase>\n"
            "      <phase id=\"2\">小步修改（每步可验证/可回滚）</phase>\n"
            "      <phase id=\"3\">验证（优先 python -m unittest）</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>避免大爆炸式重写</guard>\n"
            "      <guard>默认避免全仓库宽扫描，除非用户明确要求“全量/全局/全仓库”</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>重构目标与理由</section>\n"
            "      <section>修改计划</section>\n"
            "      <section>修改摘要</section>\n"
            "      <section>验证步骤</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def init_state(self, user_input: str) -> Dict[str, Any]:
        s = DefaultPolicy().init_state(user_input)
        s["handoff_only"] = False
        return s

    def effective_permission(self, base: ToolPermission, state: Dict[str, Any]) -> ToolPermission:
        if state.get("handoff_only"):
            return ToolPermission(allowed_tools=[], restricted_tools=sorted(set(base.restricted_tools or [])))
        return base

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        if state.get("handoff_only"):
            return PolicyDecision(
                allowed=False,
                reason="🛑 策略早停：当前为 handoff_only 模式，仅允许基于交接单输出计划/清单；不要继续调用工具。",
            )

        base_decision = DefaultPolicy().validate_tool_call(tool_name, args, state)
        if not base_decision.allowed:
            return base_decision

        handoff = state.get("handoff") or {}
        already_read = set(handoff.get("read_files") or [])

        if tool_name == "file_read":
            path = str(args.get("path", ""))
            if path and path in already_read and not args.get("allow_reread"):
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：交接单显示该文件已读，默认禁止重复 file_read。若确需重复，请在参数中加入 allow_reread=true 并尽量只读取必要片段。",
                )

        if tool_name == "shell_command":
            user_text = (state.get("user_input") or "")
            explicit = any(k in user_text for k in ["运行", "启动", "执行命令", "run", "start"])
            if not explicit and not args.get("allow_shell"):
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：Refactor 默认不执行 shell_command（跑应用/查DB/探测服务）。如需执行，请用户明确要求或切换到 Test/Run 流程。",
                )
            command = str(args.get("command", ""))
            if len(command) > 500:
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：shell_command 参数过长，容易导致 Token 爆炸。请改用更短命令或拆分步骤。",
                )
            state["_shell_attempts"] = int(state.get("_shell_attempts") or 0) + 1
            if int(state["_shell_attempts"]) > 1:
                return PolicyDecision(
                    allowed=False,
                    reason="⛔ 策略拒绝：Refactor 的 shell_command 调用次数已达预算上限。请改为输出验证步骤或切换到 Test/Run。",
                )

        return PolicyDecision(allowed=True)


class ArchitectPolicy(SubAgentPolicy):
    name = "architect"

    def policy_prompt(self, state: Dict[str, Any]) -> str:
        return (
            "<policy_prompt>\n"
            f"  <policy name=\"{self.name}\">\n"
            "    <goals>\n"
            "      <goal>只读分析：基于现有代码提出架构/API 方案与验收清单</goal>\n"
            "    </goals>\n"
            "    <workflow>\n"
            "      <phase id=\"1\">收集证据（结构/依赖/关键模块）</phase>\n"
            "      <phase id=\"2\">方案（模块边界/接口/数据流）</phase>\n"
            "      <phase id=\"3\">迁移步骤（最小风险优先）</phase>\n"
            "      <phase id=\"4\">验收清单</phase>\n"
            "    </workflow>\n"
            "    <guards>\n"
            "      <guard>只读：不执行写入/删除/命令</guard>\n"
            "      <guard>先给现状证据，再给方案与验收清单</guard>\n"
            "      <guard>默认避免全仓库宽扫描，除非用户明确要求“全量/全局/全仓库”</guard>\n"
            "    </guards>\n"
            "    <output>\n"
            "      <section>现状概览</section>\n"
            "      <section>目标方案</section>\n"
            "      <section>迁移步骤</section>\n"
            "      <section>验收清单</section>\n"
            "    </output>\n"
            "  </policy>\n"
            "</policy_prompt>\n"
        )

    def init_state(self, user_input: str) -> Dict[str, Any]:
        return DefaultPolicy().init_state(user_input)

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> PolicyDecision:
        return DefaultPolicy().validate_tool_call(tool_name, args, state)
