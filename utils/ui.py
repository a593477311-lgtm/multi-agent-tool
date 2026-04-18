from rich.console import Console
from dataclasses import dataclass, field
from typing import Dict, Any, List
import time
import re

console = Console()

class DisplayMode:
    expanded: bool = False
    
    def toggle(self) -> str:
        self.expanded = not self.expanded
        return "展开模式" if self.expanded else "折叠模式"
    
    def is_expanded(self) -> bool:
        return self.expanded

display_mode = DisplayMode()

@dataclass
class SessionStats:
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    start_time: float = 0.0
    last_input_tokens: int = 0
    last_output_tokens: int = 0
    last_elapsed: float = 0.0
    tool_costs: List[Dict[str, Any]] = field(default_factory=list)
    model_id: str = ""
    
    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
    
    def add_tokens(self, input_tokens: int, output_tokens: int):
        self.last_input_tokens = input_tokens
        self.last_output_tokens = output_tokens
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost = calculate_cost(self.total_input_tokens, self.total_output_tokens, self.model_id)
    
    def add_tool_cost(self, tool_name: str, input_tokens: int, output_tokens: int, cost: float):
        self.tool_costs.append({
            "tool": tool_name,
            "input": input_tokens,
            "output": output_tokens,
            "cost": cost
        })
    
    def get_elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    def get_last_cost(self) -> float:
        return calculate_cost(self.last_input_tokens, self.last_output_tokens, self.model_id)
    
    def set_model_id(self, model_id: str):
        self.model_id = model_id

def calculate_cost(input_tokens: int, output_tokens: int, model_id: str = "") -> float:
    from config.models import get_model_price
    
    prices = get_model_price(model_id) if model_id else {"input": 2.0, "output": 2.0}
    input_cost = (input_tokens / 1_000_000) * prices["input"]
    output_cost = (output_tokens / 1_000_000) * prices["output"]
    return input_cost + output_cost

def format_stats_line(input_tokens: int, output_tokens: int, elapsed: float, cost: float) -> str:
    return f"📊 本次: ¥{cost:.4f} | 耗时: {elapsed:.1f}s | Token: ↑{input_tokens:,} ↓{output_tokens:,}"

def format_result_summary(tool_name: str, result: str, args: dict = None) -> str:
    if not result:
        return f"📌 {tool_name} → (空结果)"
    
    def get_path_from_args():
        if args:
            return args.get("path", args.get("file_path", "未知"))
        return "未知"
    
    def get_short_path(path: str) -> str:
        parts = path.replace("\\", "/").split("/")
        if len(parts) > 3:
            return "/".join(parts[-3:])
        return path
    
    if tool_name == "file_read":
        path = get_short_path(get_path_from_args())
        lines = result.count('\n') + 1
        truncated = "已截断" if "截断" in result or "truncated" in result.lower() or lines > 2000 else ""
        if truncated:
            return f"📄 {path} ({lines}行, 已截断)"
        return f"📄 {path} ({lines}行)"
    
    elif tool_name == "file_write":
        path = get_short_path(get_path_from_args())
        content = args.get("content", "") if args else ""
        size = len(content)
        return f"✅ {path} ({size} bytes)"
    
    elif tool_name == "list_dir":
        path = get_short_path(get_path_from_args())
        file_count = result.count("[文件]") + result.count("file") + result.count("文件")
        dir_count = result.count("[目录]") + result.count("directory") + result.count("目录")
        lines = result.strip().split('\n') if result.strip() else []
        if file_count == 0 and dir_count == 0 and lines:
            for line in lines:
                if "文件" in line or "file" in line.lower():
                    try:
                        import re
                        match = re.search(r'(\d+)\s*(个?\s*文件)', line)
                        if match:
                            file_count = int(match.group(1))
                    except:
                        pass
                if "目录" in line or "dir" in line.lower():
                    try:
                        import re
                        match = re.search(r'(\d+)\s*(个?\s*目录)', line)
                        if match:
                            dir_count = int(match.group(1))
                    except:
                        pass
        return f"📁 {path} ({file_count}个文件, {dir_count}个目录)"
    
    elif tool_name == "grep":
        lines = [l for l in result.strip().split('\n') if l.strip()]
        match_count = len(lines)
        if match_count == 0 or (match_count == 1 and ("无匹配" in result or "no match" in result.lower())):
            return "🔍 无匹配"
        return f"🔍 {match_count}个匹配"
    
    elif tool_name == "glob":
        lines = [l for l in result.strip().split('\n') if l.strip()]
        file_count = len(lines)
        return f"📋 {file_count}个文件"
    
    elif tool_name == "shell_command":
        lines = result.strip().split('\n') if result.strip() else []
        line_count = len(lines)
        if line_count == 0 or (line_count == 1 and not result.strip()):
            return "$ 执行成功"
        return f"$ {line_count}行输出"
    
    elif tool_name == "project_structure":
        return "📊 结构分析完成"
    
    elif tool_name == "dependency":
        return "📦 依赖分析完成"
    
    elif tool_name == "symbol":
        lines = [l for l in result.strip().split('\n') if l.strip()]
        symbol_count = len(lines)
        return f"🔍 {symbol_count}个符号"
    
    elif tool_name == "search_replace":
        import re
        match = re.search(r'(\d+)\s*处', result)
        if match:
            count = match.group(1)
        else:
            count = "1"
        return f"✅ 已替换 {count} 处"
    
    elif tool_name == "mkdir":
        return "📁 已创建目录"
    
    elif tool_name == "file_delete":
        return "🗑️ 已删除"
    
    elif tool_name == "http_request":
        import re
        status_match = re.search(r'状态码[：:]\s*(\d+)', result)
        if status_match:
            status = status_match.group(1)
        else:
            status_match = re.search(r'status[：:]\s*(\d+)', result, re.IGNORECASE)
            if status_match:
                status = status_match.group(1)
            else:
                status_match = re.search(r'(\d{3})', result)
                status = status_match.group(1) if status_match else "未知"
        return f"🌐 状态码: {status}"
    
    elif tool_name == "TodoWrite":
        import re
        completed = len(re.findall(r'✅', result))
        in_progress = len(re.findall(r'🔄', result))
        pending = len(re.findall(r'⏳', result))
        total = completed + in_progress + pending
        if total == 0:
            return "📋 任务列表已清空"
        
        has_changes = "任务状态变更" in result
        change_summary = ""
        if has_changes:
            changes = re.findall(r'- (.+?): (⏳|🔄|✅) (\w+) → (⏳|🔄|✅) (\w+)', result)
            if changes:
                change_summary = f" | 📝 {len(changes)}个状态变更"
        
        return f"📋 任务列表: {total}个任务 (✅{completed} 🔄{in_progress} ⏳{pending}){change_summary}"
    
    else:
        if len(result) > 100:
            return f"{result[:100]}..."
        return result

def print_error(error_type: str, reason: str, suggestion: str = None):
    console.print(f"\n[red bold]❌ 错误:[/red bold] {error_type}")
    console.print(f"[red]📝 原因:[/red] {reason}")
    if suggestion:
        console.print(f"[yellow]💡 建议:[/yellow] {suggestion}")

def print_success(message: str):
    console.print(f"[green]✅ {message}[/green]")

def print_warning(message: str):
    console.print(f"[yellow]⚠️ {message}[/yellow]")

def print_info(message: str):
    console.print(f"[cyan]ℹ️ {message}[/cyan]")

def print_stats(input_tokens: int, output_tokens: int, elapsed: float, model_id: str = ""):
    cost = calculate_cost(input_tokens, output_tokens, model_id)
    stats_line = format_stats_line(input_tokens, output_tokens, elapsed, cost)
    console.print(f"\n[dim]{stats_line}[/dim]")

def print_help():
    console.print("\n[bold yellow]📖 对话管理[/bold yellow]")
    console.print("  /save       - 保存当前会话")
    console.print("  /load       - 加载历史会话")
    console.print("  /clear      - 清除对话历史")
    console.print("  /fork       - 创建会话分支")
    console.print("  /forks      - 列出所有会话分支")
    console.print("  /resume <id>- 恢复指定会话")
    
    console.print("\n[bold yellow]🔧 工具与调试[/bold yellow]")
    console.print("  /tools      - 显示可用工具")
    console.print("  /thinking   - 开启思考模式")
    console.print("  /unthinking - 关闭思考模式")
    console.print("  /model      - 显示/切换模型")
    console.print("  /expand     - 切换展开/折叠模式")
    console.print("  /analyze    - 分析项目结构")
    
    console.print("\n[bold yellow]📊 信息查看[/bold yellow]")
    console.print("  /info       - 显示对话状态")
    console.print("  /context    - 显示上下文使用情况")
    console.print("  /cost       - 显示累计 Token 和费用")
    console.print("  /history    - 查看变更历史")
    
    console.print("\n[bold yellow]⚙️ 任务控制[/bold yellow]")
    console.print("  /continue   - 继续执行暂停的任务")
    console.print("  /status     - 显示当前任务状态")
    console.print("  /stop       - 停止当前任务")
    console.print("  /undo       - 撤销最近变更")
    console.print("  /redo       - 重做已撤销的变更")
    console.print("  /compress   - 手动压缩上下文")
    
    console.print("\n[bold yellow]🖥️ 后台进程[/bold yellow]")
    console.print("  /jobs       - 查看后台进程列表")
    console.print("  /kill <id>  - 终止指定进程")
    console.print("  /logs <id>  - 查看进程输出")
    console.print("  /cleanup    - 清理过期进程记录")
    
    console.print("\n[bold yellow]🔌 MCP工具[/bold yellow]")
    console.print("  /tools      - 显示原生工具和MCP工具")
    console.print("  MCP工具以绿色显示，由外部服务提供")
    
    console.print("\n[dim]输入 exit 退出程序[/dim]\n")

def print_context_usage(usage_percent: float, message_count: int):
    bar_width = 20
    filled = int(usage_percent * bar_width)
    empty = bar_width - filled
    
    if usage_percent < 0.5:
        color = "green"
    elif usage_percent < 0.85:
        color = "yellow"
    else:
        color = "red"
    
    bar = f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"
    
    console.print(f"\n[bold]上下文使用情况[/bold]")
    console.print(f"进度: {bar} {usage_percent*100:.1f}%")
    console.print(f"消息数: {message_count}")

def print_cost(session_stats: SessionStats):
    console.print(f"\n[bold]累计费用统计[/bold]")
    console.print(f"输入 Token: {session_stats.total_input_tokens:,}")
    console.print(f"输出 Token: {session_stats.total_output_tokens:,}")
    console.print(f"累计费用: ¥{session_stats.total_cost:.4f}")
    console.print(f"会话时长: {session_stats.get_elapsed_time():.1f}s")
    
    if session_stats.tool_costs:
        console.print(f"\n[bold]工具调用成本分解:[/bold]")
        for tc in session_stats.tool_costs[-10:]:
            console.print(f"  {tc['tool']}: ↑{tc['input']} ↓{tc['output']} = ¥{tc['cost']:.4f}")

def print_session_restore(session_info: dict):
    console.print(f"\n[cyan]📂 恢复会话:[/cyan] {session_info.get('session_start', '未知')} ({session_info.get('message_count', 0)}条消息)")
    console.print(f"[dim]可用命令: /status /compact /cost[/dim]")

class UIEventHandler:
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"
    
    def _emit(self, color: str, text: str):
        print(f"{color}{text}{self.RESET}")

    def _tag(self, xml_text: str, name: str) -> str:
        m = re.search(rf"<{name}>(.*?)</{name}>", xml_text, flags=re.DOTALL | re.IGNORECASE)
        return (m.group(1).strip() if m else "")

    def on_route(self, task_type: str, subagent: str = None, collaboration_chain: str = None):
        if collaboration_chain:
            self._emit(self.MAGENTA, f"🧭 路由：{task_type} | 🤝 协作链：{collaboration_chain}")
            return
        if subagent:
            self._emit(self.MAGENTA, f"🧭 路由：{task_type} | 🧩 子Agent：{subagent}")
            return
        self._emit(self.MAGENTA, f"🧭 路由：{task_type}")

    def on_subagent_start(self, name: str):
        self._emit(self.MAGENTA, f"🧩 子Agent：{name}")

    def on_stage(self, stage: str):
        self._emit(self.MAGENTA, f"📍 阶段：{stage}")

    def on_policy_event(self, text: str):
        raw = (text or "").strip()
        if not raw:
            return
        if display_mode.is_expanded():
            self._emit(self.CYAN, raw)
            return
        if "<decision>" in raw:
            dtype = self._tag(raw, "type")
            policy = self._tag(raw, "policy")
            src = self._tag(raw, "from")
            dst = self._tag(raw, "to")
            reason = self._tag(raw, "reason")
            if dtype == "policy_level_upgrade":
                label = "🔺 策略升级"
            elif dtype:
                label = f"🧠 {dtype}"
            else:
                label = "🧠 决策"
            parts = []
            if policy:
                parts.append(policy)
            if src or dst:
                parts.append(f"{src or '?'} → {dst or '?'}")
            if reason:
                parts.append(f"原因：{reason}")
            body = "｜".join([p for p in parts if p])
            self._emit(self.CYAN, f"{label}：{body}".strip())
            return
        if raw.startswith(("🛑", "⛔", "✅", "⚠️", "ℹ️")):
            self._emit(self.CYAN, raw)
            return
        self._emit(self.CYAN, f"🧠 策略提示：{raw}")

    def on_tool_call(self, tool_name: str, args: dict = None):
        output = f"{self.YELLOW}📌 {tool_name}{self.RESET}"
        if args:
            key_args = []
            for key in ["path", "file_path", "command", "pattern", "query"]:
                if key in args:
                    value = args[key]
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:50] + "..."
                    key_args.append(f"{key}={repr(value)}")
            if key_args:
                output += f" ({', '.join(key_args)})"
        print(output)
    
    def on_tool_result(self, tool_name: str, result: str, args: dict = None):
        summary = format_result_summary(tool_name, result, args)
        print(f"{self.CYAN}{summary}{self.RESET}")
    
    def on_thinking(self, chunk: str):
        print(chunk, end="", flush=True)
    
    def on_content(self, chunk: str):
        print(f"{self.GREEN}{chunk}{self.RESET}", end="", flush=True)
    
    def on_parallel_start(self, count: int):
        print(f"{self.YELLOW}🔧 并行执行 {count} 个工具...{self.RESET}")
    
    def on_parallel_complete(self, success: int, total: int):
        print(f"{self.CYAN}📊 完成: {success}/{total} 成功{self.RESET}")
    
    def on_subagent_call(self, name: str, reason: str = None):
        print(f"{self.MAGENTA}🧩 调用子Agent：{name}{self.RESET}")
        if reason:
            print(f"{self.CYAN}   原因：{reason}{self.RESET}")

__all__ = [
    'console',
    'SessionStats',
    'print_help',
    'print_context_usage',
    'print_cost',
    'print_error',
    'print_success',
    'print_warning',
    'print_info',
    'print_stats',
    'display_mode',
    'print_session_restore',
    'UIEventHandler',
    'format_result_summary',
]
