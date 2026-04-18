import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.align import Align

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

from agent import Agent
from agent.change_history import ChangeHistory
from tools import (
    FileReadTool,
    FileWriteTool,
    ListDirTool,
    MkdirTool,
    FileDeleteTool,
    ShellCommandTool,
    HTTPRequestTool,
    GlobTool,
    GrepTool,
    SearchReplaceTool,
    ProjectStructureTool,
    DependencyTool,
    SymbolTool,
    TodoWriteTool,
    SubagentTool,
    ProjectPrecheckTool,
)
from config import validate_config, set_work_dir, get_work_dir
from config.models import get_all_models, get_default_model, model_exists
from utils.logger import init_file_logger, get_logger
from mcp import MCPConfig, MCPClientManager
from utils.ui import (
    console, SessionStats, print_help, print_context_usage, print_cost,
    print_error, print_success, print_warning, print_info, print_stats,
    display_mode, print_session_restore, UIEventHandler
)

logger = get_logger()

AVAILABLE_COMMANDS = [
    "/help", "/clear", "/info", "/tools", "/model", "/save", "/load",
    "/compress", "/expand", "/context", "/cost", "/fork", "/forks",
    "/resume", "/pwd", "/thinking", "/th", "/unthinking", "/unth",
    "/analyze", "/history", "/undo", "/redo", "/continue", "/c", "/status",
    "/stop", "/cd", "/jobs", "/kill", "/logs", "/cleanup", "/todos", "exit"
]

command_completer = WordCompleter(AVAILABLE_COMMANDS, ignore_case=True)

LOGO_LINES = [
    " ███████╗██╗  ██╗ ██████╗ ██╗   ██╗██╗   ██╗ ██████╗ ███████╗",
    " ╚══███╔╝██║  ██║██╔═══██╗██║   ██║╚██╗ ██╔╝██╔═══██╗██╔════╝",
    "   ███╔╝ ███████║██║   ██║██║   ██║ ╚████╔╝ ██║   ██║███████╗",
    "  ███╔╝  ██╔══██║██║   ██║██║   ██║  ╚██╔╝  ██║   ██║╚════██║",
    " ███████╗██║  ██║╚██████╔╝╚██████╔╝   ██║   ╚██████╔╝███████║",
    " ╚══════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝    ╚═╝    ╚═════╝ ╚══════╝",
]

SUB_TEXT_PREFIX = ">>  来 自 艾 卡 西 亚 的 "
SUB_TEXT_HIGHLIGHT = "骤 雨"
SUB_TEXT_SUFFIX = "  <<"

VERTICAL_GRADIENT = [
    "bold spring_green1",
    "bold cyan",
    "bold deep_sky_blue1",
    "bold blue",
    "bold dark_blue",
    "bold blue",
]

CORE_HIGHLIGHT = "bold white"
EDGE_COLORS = ["cyan", "deep_sky_blue1", "blue"]

RAIN_CHARS_FOREGROUND = ["|", "!", "i", "│", "‖"]
RAIN_CHARS_BACKGROUND = ["[", "]", "{", "}", "(", ")", "<", ">"]
RAIN_CHARS_SPLASH = ["*", "✦", "✧", "+", "°"]
RAIN_CHARS_LIGHT = [".", ":", "·"]
GLITCH_CHARS = ["~", "#", "%", "&", "@", "█", "▓", "░", "▒"]

FOREGROUND_COLORS = ["bold cyan", "bold deep_sky_blue1", "bold spring_green1", "bold magenta"]
BACKGROUND_COLORS = ["dim blue", "dim dark_blue", "dim blue3", "dim deep_sky_blue4"]
TRAIL_COLORS = ["dim cyan", "dim blue", "dim dark_blue"]

SYSTEM_MSGS = [
    "[LOADING... 77%]",
    "[ERR_VOID_DECODE]",
    "[AUTH: KAI'SA]",
    "[SIGNAL: WEAK]",
    "[SYNC: 0.847]",
    "[NODE: ACTIVE]",
    "[FLUX: DETECTED]",
    "[VOID: UNSTABLE]",
]

HEX_ADDRESSES = ["0x00A15F", "0x7F3D2B", "0xVOID42", "0x1C4DEA", "0xBADCODE"]
BORDER_TAGS = ["SEC_LEVEL: 5", "V_SCAN: ACTIVE", "VOID_LOCK", "NULL_PTR", "FLUX_MODE"]

class Lightning:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.bolt = []
        self.timer = 0
        self.active = False
    
    def update(self):
        self.timer += 1
        if self.active:
            self.active = False
            self.bolt = []
        if self.timer > random.randint(50, 120):
            self.timer = 0
            self.active = True
            self.bolt = self._generate_bolt()
    
    def _generate_bolt(self):
        bolt = []
        x = self.width - random.randint(1, 3)
        y = 0
        bolt.append((x, y))
        target_x = random.randint(0, 2)
        while y < self.height - 1:
            y += 1
            if x > target_x:
                dx = random.choice([-3, -2, -2, -1, -1, 0])
            else:
                dx = random.choice([-1, 0, 0, 1, 1, 2])
            x += dx
            x = max(0, min(self.width - 1, x))
            bolt.append((x, y))
            if random.random() > 0.6:
                branch_len = random.randint(1, 3)
                bx, by = x, y
                branch_dir = random.choice([-1, 1])
                for _ in range(branch_len):
                    bx += branch_dir
                    by += random.randint(0, 1)
                    if 0 <= bx < self.width and 0 <= by < self.height:
                        bolt.append((bx, by))
        return bolt
    
    def is_lightning(self, x, y):
        return (x, y) in self.bolt

class GlitchEffect:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.glitches = []
        self.line_shifts = {}
        self.timer = 0
        self.flash_pixel = None
        self.scanline_y = -1
    
    def update(self):
        self.timer += 1
        if self.timer > random.randint(20, 50):
            self.timer = 0
            self.glitches = []
            num_glitches = random.randint(2, 6)
            for _ in range(num_glitches):
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                char = random.choice(GLITCH_CHARS)
                self.glitches.append((x, y, char))
        if random.random() > 0.92:
            self.line_shifts = {}
            num_shifts = random.randint(1, 2)
            for _ in range(num_shifts):
                y = random.randint(1, self.height - 2)
                shift = random.choice([-2, -1, 1, 2])
                self.line_shifts[y] = shift
        elif random.random() > 0.8:
            self.line_shifts = {}
        if random.random() > 0.97:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            self.flash_pixel = (x, y, random.choice(["bold red", "bold yellow", "bold white"]))
        elif random.random() > 0.7:
            self.flash_pixel = None
        if random.random() > 0.85:
            self.scanline_y = random.randint(2, self.height - 2)
        else:
            self.scanline_y = -1
    
    def get_glitch(self, x, y):
        for gx, gy, char in self.glitches:
            if gx == x and gy == y:
                return char
        return None
    
    def get_line_shift(self, y):
        return self.line_shifts.get(y, 0)
    
    def get_flash_pixel(self, x, y):
        if self.flash_pixel and self.flash_pixel[0] == x and self.flash_pixel[1] == y:
            return self.flash_pixel[2]
        return None
    
    def is_scanline(self, y):
        return y == self.scanline_y

class CyberBorder:
    def __init__(self, width):
        self.width = width
        self.gaps_top = []
        self.gaps_bottom = []
        self.border_tag = random.choice(BORDER_TAGS)
        self.hex_addr = random.choice(HEX_ADDRESSES)
        self.leaking_pixels = []
        self.frame_count = 0
    
    def update(self):
        self.frame_count += 1
        if self.frame_count % 10 == 0:
            self.gaps_top = []
            self.gaps_bottom = []
            num_gaps = random.randint(1, 3)
            for _ in range(num_gaps):
                gap_pos = random.randint(5, self.width - 10)
                gap_len = random.randint(2, 5)
                self.gaps_top.append((gap_pos, gap_len))
            num_gaps = random.randint(1, 2)
            for _ in range(num_gaps):
                gap_pos = random.randint(5, self.width - 10)
                gap_len = random.randint(1, 3)
                self.gaps_bottom.append((gap_pos, gap_len))
        if self.frame_count % 15 == 0:
            self.border_tag = random.choice(BORDER_TAGS)
            self.hex_addr = random.choice(HEX_ADDRESSES)
        self.leaking_pixels = []
        for _ in range(random.randint(3, 8)):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, 2)
            char = random.choice([".", ",", "·", "°"])
            self.leaking_pixels.append((x, y, char))
    
    def _apply_gaps(self, line, gaps):
        result = list(line)
        for pos, length in gaps:
            for i in range(pos, min(pos + length, len(result))):
                if i < len(result):
                    if random.random() > 0.5:
                        result[i] = random.choice(["0x", "EF", "NULL", "##", "  "][0])
                    else:
                        result[i] = " "
        return "".join(result)
    
    def build_top_border(self, title):
        inner_width = self.width - 4
        tag = f"[ {self.border_tag} ]"
        tag_len = len(tag)
        left_len = (inner_width - tag_len) // 2 - len(title) // 2 - 2
        right_len = inner_width - tag_len - left_len - len(title) - 4
        left_len = max(3, left_len)
        right_len = max(3, right_len)
        left_line = "═" * left_len
        right_line = "═" * right_len
        left_line = self._apply_gaps(left_line, self.gaps_top)
        right_line = self._apply_gaps(right_line, self.gaps_top)
        border = Text()
        border.append("╔", style="bold cyan")
        border.append(left_line, style="cyan")
        border.append(f" {title} ", style="bold cyan")
        border.append("═", style="cyan")
        border.append(tag, style="dim magenta")
        border.append(right_line, style="cyan")
        border.append("╗", style="bold cyan")
        return border
    
    def build_bottom_border(self, load_percent):
        inner_width = self.width - 4
        load_bar = "█" * (load_percent // 10) + "░" * (10 - load_percent // 10)
        status = f"[ {load_bar} {load_percent}% ]"
        status_len = len(status)
        left_len = 5
        right_len = inner_width - status_len - left_len - 2
        right_len = max(3, right_len)
        left_line = "─" * left_len
        right_line = "─" * right_len
        left_line = self._apply_gaps(left_line, self.gaps_bottom)
        right_line = self._apply_gaps(right_line, self.gaps_bottom)
        border = Text()
        border.append("╚", style="bold cyan")
        border.append(left_line, style="dim cyan")
        border.append("■ ", style="dim blue")
        border.append(status, style="dim cyan")
        border.append(right_line, style="dim cyan")
        border.append("╝", style="bold cyan")
        return border
    
    def get_leaking_pixel(self, x, y):
        for px, py, char in self.leaking_pixels:
            if px == x and py == y:
                return char
        return None

class CyberRain:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rain = [[" " for _ in range(width)] for _ in range(height)]
        self.rain_types = [[None for _ in range(width)] for _ in range(height)]
        self.rain_colors = [[None for _ in range(width)] for _ in range(height)]
        self.lightning = Lightning(width, height)
        self.glitch = GlitchEffect(width, height)
        self.border = CyberBorder(width + 4)
        self.color_offset = 0
        self.frame_count = 0
        self.system_msg = random.choice(SYSTEM_MSGS)
        self.load_percent = 77
        self.splash_positions = set()
        self.exclamation_visible = True
    
    def update(self):
        if self.rain:
            self.rain.pop(-1)
            self.rain_types.pop(-1)
            self.rain_colors.pop(-1)
        new_row = []
        new_types = []
        new_colors = []
        for i in range(self.width):
            if random.random() > 0.72:
                char_type = random.random()
                if char_type > 0.8:
                    char = random.choice(RAIN_CHARS_BACKGROUND)
                    rtype = "background"
                    color = random.choice(BACKGROUND_COLORS)
                elif char_type > 0.4:
                    char = random.choice(RAIN_CHARS_FOREGROUND)
                    rtype = "foreground"
                    color = random.choice(FOREGROUND_COLORS)
                else:
                    char = random.choice(RAIN_CHARS_LIGHT)
                    rtype = "light"
                    color = random.choice(TRAIL_COLORS)
                new_row.append(char)
                new_types.append(rtype)
                new_colors.append(color)
            else:
                new_row.append(" ")
                new_types.append(None)
                new_colors.append(None)
        self.rain.insert(0, new_row)
        self.rain_types.insert(0, new_types)
        self.rain_colors.insert(0, new_colors)
        self.lightning.update()
        self.glitch.update()
        self.border.update()
        if random.random() > 0.95:
            self.system_msg = random.choice(SYSTEM_MSGS)
        self.load_percent = min(100, max(0, self.load_percent + random.randint(-3, 3)))
        self.exclamation_visible = random.random() > 0.3
        self.splash_positions = set()
        padding = 2
        logo_start_y = 1
        logo_start_x = padding
        for y in range(len(self.rain)):
            for x in range(len(self.rain[y])):
                if logo_start_y <= y < logo_start_y + len(LOGO_LINES):
                    logo_line = LOGO_LINES[y - logo_start_y]
                    if logo_start_x <= x < logo_start_x + len(logo_line):
                        logo_char = logo_line[x - logo_start_x]
                        if logo_char != " ":
                            if random.random() > 0.85:
                                splash_x = x + random.randint(-1, 1)
                                splash_y = y - 1
                                if 0 <= splash_x < self.width and 0 <= splash_y < self.height:
                                    self.splash_positions.add((splash_x, splash_y))
        self.frame_count += 1
        if self.frame_count >= 3:
            self.frame_count = 0
            self.color_offset = (self.color_offset + 1) % len(VERTICAL_GRADIENT)
    
    def _get_logo_color(self, x, y, logo_start_x, logo_start_y):
        rel_y = y - logo_start_y
        rel_x = x - logo_start_x
        logo_line = LOGO_LINES[rel_y]
        char_positions = [i for i, c in enumerate(logo_line) if c != " "]
        if not char_positions:
            return VERTICAL_GRADIENT[0]
        min_x = min(char_positions)
        max_x = max(char_positions)
        char_center = (min_x + max_x) / 2
        dist_from_center = abs(rel_x - char_center)
        max_dist = (max_x - min_x) / 2
        if dist_from_center < max_dist * 0.25:
            return CORE_HIGHLIGHT
        elif dist_from_center < max_dist * 0.5:
            color_idx = min(rel_y + self.color_offset, len(VERTICAL_GRADIENT) - 1)
            return VERTICAL_GRADIENT[color_idx]
        else:
            return random.choice(EDGE_COLORS)
    
    def __rich__(self):
        content = Text()
        title = f"ICATHIAN RAIN [{self.border.hex_addr}]"
        content.append(self.border.build_top_border(title))
        content.append("\n")
        padding = 2
        logo_start_y = 1
        logo_start_x = padding
        for y, row in enumerate(self.rain):
            is_scanline = self.glitch.is_scanline(y)
            content.append("║", style="cyan")
            content.append(" ", style="default")
            if is_scanline:
                scanline = "─" * self.width
                content.append(scanline, style="dim blue")
            else:
                for i, ch in enumerate(row):
                    is_logo = False
                    is_lightning = self.lightning.is_lightning(i, y)
                    glitch_char = self.glitch.get_glitch(i, y)
                    flash_color = self.glitch.get_flash_pixel(i, y)
                    is_splash = (i, y) in self.splash_positions
                    leak_char = self.border.get_leaking_pixel(i, y)
                    if logo_start_y <= y < logo_start_y + len(LOGO_LINES):
                        logo_line = LOGO_LINES[y - logo_start_y]
                        if logo_start_x <= i < logo_start_x + len(logo_line):
                            logo_char = logo_line[i - logo_start_x]
                            if logo_char != " ":
                                if is_lightning:
                                    content.append(logo_char, style="bold red")
                                elif glitch_char:
                                    content.append(glitch_char, style="bold red")
                                elif flash_color:
                                    content.append(logo_char, style=flash_color)
                                else:
                                    color = self._get_logo_color(i, y, logo_start_x, logo_start_y)
                                    content.append(logo_char, style=color)
                                is_logo = True
                    if not is_logo:
                        if is_lightning:
                            content.append("⚡", style="bold red")
                        elif glitch_char:
                            content.append(glitch_char, style="bold red")
                        elif flash_color:
                            content.append(random.choice(GLITCH_CHARS), style=flash_color)
                        elif is_splash:
                            content.append(random.choice(RAIN_CHARS_SPLASH), style="bold cyan")
                        elif leak_char and ch == " ":
                            content.append(leak_char, style="dim cyan")
                        elif ch != " ":
                            color = self.rain_colors[y][i] if y < len(self.rain_colors) and i < len(self.rain_colors[y]) else "cyan"
                            content.append(ch, style=color)
                        else:
                            content.append(ch)
            content.append(" ", style="default")
            content.append("║", style="cyan")
            content.append("\n")
        sub_y = logo_start_y + len(LOGO_LINES) + 1
        if sub_y < self.height:
            content.append("║", style="cyan")
            content.append(" ", style="default")
            content.append("  " + SUB_TEXT_PREFIX, style="dim cyan")
            if self.frame_count % 2 == 0:
                content.append(SUB_TEXT_HIGHLIGHT, style="bold yellow")
            else:
                content.append(SUB_TEXT_HIGHLIGHT, style="bold cyan")
            content.append(SUB_TEXT_SUFFIX, style="dim cyan")
            content.append("  ", style="default")
            content.append(self.system_msg, style="dim magenta")
            if self.exclamation_visible:
                content.append(" ", style="default")
                content.append("!", style="bold red blink")
            remaining = self.width - 50
            if remaining > 0:
                content.append(" " * remaining, style="default")
            content.append(" ", style="default")
            content.append("║", style="cyan")
            content.append("\n")
        content.append(self.border.build_bottom_border(self.load_percent))
        return content

def show_banner(duration: float = 3.0):
    padding = 2
    logo_width = len(LOGO_LINES[0]) + padding * 2
    logo_height = len(LOGO_LINES) + 4
    rain_effect = CyberRain(logo_width, logo_height)
    start_time = time.time()
    with Live(screen=True, refresh_per_second=15) as live:
        while time.time() - start_time < duration:
            rain_effect.update()
            live.update(rain_effect)
            time.sleep(0.067)
    console.print(rain_effect)

def select_workspace() -> Path:
    console.print("\n[cyan]📁 请选择工作区目录:[/cyan]")
    console.print("  1. 当前目录")
    console.print("  2. 用户主目录")
    console.print("  3. 自定义路径")
    
    while True:
        try:
            choice = prompt("请选择 (1/2/3): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]已取消[/yellow]")
            sys.exit(0)
        
        if choice == "1":
            workspace = Path.cwd()
            break
        elif choice == "2":
            workspace = Path.home()
            break
        elif choice == "3":
            try:
                custom_path = prompt("请输入路径: ").strip()
                workspace = Path(custom_path)
                if not workspace.exists():
                    create = prompt("路径不存在，是否创建? (y/n): ").strip().lower()
                    if create == 'y':
                        workspace.mkdir(parents=True, exist_ok=True)
                    else:
                        continue
                break
            except Exception as e:
                console.print(f"[red]路径无效: {e}[/red]")
                continue
        else:
            console.print("[red]无效选择，请重新输入[/red]")
    
    return workspace

def select_platform() -> str:
    from config import set_platform, NVIDIA_API_KEY, SILICONFLOW_API_KEY, ALIYUN_API_KEY
    
    available_platforms = []
    if NVIDIA_API_KEY.strip():
        available_platforms.append("nvidia")
    if SILICONFLOW_API_KEY.strip():
        available_platforms.append("siliconflow")
    if ALIYUN_API_KEY.strip():
        available_platforms.append("aliyun")
    
    if len(available_platforms) == 0:
        console.print("[red]错误：未配置任何平台的 API Key[/red]")
        sys.exit(1)
    
    if len(available_platforms) == 1:
        platform = available_platforms[0]
        set_platform(platform)
        platform_names = {
            "nvidia": "NVIDIA NIM",
            "siliconflow": "硅基流动",
            "aliyun": "阿里云百炼"
        }
        console.print(f"\n[cyan]🌐 平台: {platform_names.get(platform, platform)}[/cyan]")
        return platform
    
    platform_names = {
        "nvidia": "NVIDIA NIM",
        "siliconflow": "硅基流动 (SiliconFlow)",
        "aliyun": "阿里云百炼"
    }
    
    console.print("\n[cyan]🌐 请选择平台:[/cyan]")
    for i, p in enumerate(available_platforms, 1):
        console.print(f"  {i}. {platform_names.get(p, p)}")
    
    while True:
        try:
            choice = prompt(f"请选择 (1-{len(available_platforms)}): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]已取消[/yellow]")
            sys.exit(0)
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available_platforms):
                platform = available_platforms[idx]
                break
            else:
                console.print("[red]无效选择，请重新输入[/red]")
        except ValueError:
            if choice in available_platforms:
                platform = choice
                break
            console.print("[red]请输入数字[/red]")
    
    set_platform(platform)
    console.print(f"[green]✅ 已选择平台: {platform_names.get(platform, platform)}[/green]")
    
    return platform

def select_model() -> str:
    models = get_all_models()
    console.print("\n[cyan]🤖 请选择模型:[/cyan]")
    
    for i, model in enumerate(models, 1):
        thinking_indicator = "🧠" if model.supports_thinking else "  "
        console.print(f"  {i}. {thinking_indicator} {model.display_name}")
        console.print(f"      [dim]{model.model_id}[/dim]")
    
    default_model = get_default_model()
    
    while True:
        try:
            choice = prompt(f"\n请选择 (1-{len(models)}, 默认: {default_model.display_name}): ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]已取消[/yellow]")
            sys.exit(0)
        
        if not choice:
            return default_model.model_id
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx].model_id
            else:
                console.print("[red]无效选择，请重新输入[/red]")
        except ValueError:
            console.print("[red]请输入数字[/red]")

def init_mcp() -> tuple:
    """初始化MCP连接，返回(manager, tools)"""
    try:
        config_path = Path(__file__).parent / "mcp_config.json"
        config = MCPConfig.from_json_file(config_path)
        manager = MCPClientManager(config)
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(manager.initialize())
        tools = manager.get_all_tools()
        
        if tools:
            console.print(f"[green]✅ MCP已连接: {len(tools)}个工具[/green]")
        
        return manager, tools
    except Exception as e:
        logger.warning(f"MCP初始化失败: {e}")
        return None, []

def create_agent(model_id: str = None) -> tuple:
    """创建Agent实例，返回(agent, mcp_manager)"""
    mcp_manager, mcp_tools = init_mcp()
    
    tools = [
        FileReadTool(),
        FileWriteTool(),
        ListDirTool(),
        MkdirTool(),
        FileDeleteTool(),
        ShellCommandTool(),
        HTTPRequestTool(),
        GlobTool(),
        GrepTool(),
        SearchReplaceTool(),
        ProjectStructureTool(),
        DependencyTool(),
        SymbolTool(),
        TodoWriteTool(),
        SubagentTool(),
        ProjectPrecheckTool(),
    ]
    ui_handler = UIEventHandler()
    
    agent = Agent(
        tools=tools,
        show_reasoning=True,
        model_id=model_id,
        callbacks={
            'route': ui_handler.on_route,
            'subagent_start': ui_handler.on_subagent_start,
            'stage': ui_handler.on_stage,
            'policy_event': ui_handler.on_policy_event,
            'parallel_start': ui_handler.on_parallel_start,
            'tool_call': ui_handler.on_tool_call,
            'tool_result': ui_handler.on_tool_result,
            'content': ui_handler.on_content,
            'subagent_call': ui_handler.on_subagent_call,
        }
    )
    agent.set_ui_mode(display_mode.is_expanded())
    
    if mcp_tools:
        agent.executor.register_mcp_tools(mcp_tools)
    
    return agent, mcp_manager

def main():
    show_banner(duration=3.0)
    
    workspace = select_workspace()
    set_work_dir(workspace)
    
    from config import get_logs_dir
    init_file_logger(get_logs_dir())
    
    platform = select_platform()
    
    try:
        validate_config()
    except ValueError as e:
        print_error("配置错误", str(e), "请检查 .env 文件中的配置")
        sys.exit(1)
    
    model_id = select_model()
    agent, mcp_manager = create_agent(model_id)
    session_stats = SessionStats()
    
    if agent.has_previous_session():
        session_info = agent.get_session_info()
        if session_info:
            print_session_restore(session_info)
            
            try:
                restore = prompt("\n是否恢复上次会话? (y/n): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                restore = 'n'
            
            if restore == 'y':
                if agent.load_session():
                    print_success("会话已恢复")
                else:
                    print_error("会话恢复失败", "无法加载会话文件", "开始新会话")
            else:
                print_info("开始新会话")
    
    console.print(f"\n[green]✅ 工作区: {get_work_dir()}[/green]")
    console.print(f"[green]✅ 当前模型: {agent.get_model_display_name()}[/green]")
    console.print(f"[green]✅ 已加载工具: {', '.join(agent.executor.list_tools())}[/green]")
    print_help()
    console.print("[green]💬 开始对话 (输入 exit 退出):[/green]\n")
    
    while True:
        try:
            user_input = prompt("👤 You: ", completer=command_completer).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]👋 正在保存会话...[/yellow]")
            agent.save_session()
            if mcp_manager:
                try:
                    mcp_manager.cleanup()
                except Exception:
                    pass
            console.print("[yellow]再见！[/yellow]")
            break
        
        if not user_input:
            continue
        
        if user_input.lower() == "exit":
            filepath = agent.save_session()
            console.print(f"\n[yellow]💾 会话已保存: {filepath}[/yellow]")
            print_cost(session_stats)
            if mcp_manager:
                try:
                    mcp_manager.cleanup()
                except Exception:
                    pass
            console.print("[yellow]👋 再见！[/yellow]")
            break
        
        if user_input == "/help":
            print_help()
            continue
        
        if user_input == "/clear":
            agent.clear_memory()
            print_warning("对话历史已清除")
            continue
        
        if user_input == "/info":
            thinking_status = "🧠 开启" if agent.is_thinking_enabled() else "💭 关闭"
            console.print(f"[yellow]📊 {agent.get_conversation_summary()}[/yellow]")
            console.print(f"[yellow]📊 思考模式: {thinking_status}[/yellow]")
            continue
        
        if user_input == "/tools":
            tools = agent.executor.list_tools()
            console.print(f"[yellow]🔧 可用工具:[/yellow]")
            console.print(f"[dim]  ── 原生工具 ──[/dim]")
            native_count = 0
            mcp_count = 0
            for tool_name in tools:
                tool = agent.executor.tools[tool_name]
                desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
                is_mcp = getattr(tool, 'is_mcp', False) or getattr(tool, 'source', None) == 'mcp'
                if is_mcp:
                    mcp_count += 1
                    continue
                native_count += 1
                console.print(f"  📌 [cyan]{tool_name}[/cyan]: {desc}")
            if mcp_count > 0:
                console.print(f"[dim]  ── MCP工具 ({mcp_count}个) ──[/dim]")
                for tool_name in tools:
                    tool = agent.executor.tools[tool_name]
                    desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
                    is_mcp = getattr(tool, 'is_mcp', False) or getattr(tool, 'source', None) == 'mcp'
                    if is_mcp:
                        console.print(f"  🔌 [green]{tool_name}[/green]: {desc}")
            console.print(f"[dim]  共计: {native_count}个原生工具, {mcp_count}个MCP工具[/dim]")
            continue
        
        if user_input == "/model":
            console.print(f"\n[yellow]🤖 当前模型: {agent.get_model_display_name()}[/yellow]")
            console.print(f"[dim]   {agent.get_current_model()}[/dim]")
            console.print(f"\n[yellow]可用模型:[/yellow]")
            for m in agent.get_available_models():
                current = "✓" if m["is_current"] else " "
                thinking = "🧠" if m["supports_thinking"] else "  "
                console.print(f"  [{current}] {thinking} [cyan]{m['display_name']}[/cyan]")
                console.print(f"      [dim]{m['model_id']}[/dim]")
            console.print(f"\n[dim]使用 /model <模型ID> 切换模型[/dim]")
            continue
        
        if user_input.startswith("/model "):
            target_model = user_input[7:].strip()
            if model_exists(target_model):
                if agent.switch_model(target_model):
                    console.print(f"[green]✅ 已切换到模型: {agent.get_model_display_name()}[/green]")
                    if not agent.llm.supports_thinking and agent.is_thinking_enabled():
                        console.print("[yellow]⚠️ 当前模型不支持思考模式，已自动关闭[/yellow]")
                else:
                    print_error("切换失败", f"无法切换到模型 {target_model}")
            else:
                print_error("模型不存在", f"未找到模型: {target_model}")
                console.print("[dim]使用 /model 查看可用模型列表[/dim]")
            continue
        
        if user_input == "/save":
            filepath = agent.save_session()
            console.print(f"[yellow]💾 会话已保存: {filepath}[/yellow]")
            continue
        
        if user_input == "/load":
            if agent.has_previous_session():
                if agent.load_session():
                    print_success("会话已加载")
                else:
                    print_error("会话加载失败", "无法加载会话文件")
            else:
                print_info("没有历史会话")
            continue
        
        if user_input == "/compress":
            result = agent.compress_context()
            console.print(f"[yellow]📦 {result}[/yellow]")
            continue
        
        if user_input == "/expand":
            mode = display_mode.toggle()
            console.print(f"[magenta]📐 已切换到{mode}[/magenta]")
            agent.set_ui_mode(display_mode.is_expanded())
            continue
        
        if user_input == "/context":
            usage = agent.memory.get_context_usage_percent()
            msg_count = len(agent.memory.messages)
            print_context_usage(usage, msg_count)
            continue
        
        if user_input == "/cost":
            print_cost(session_stats)
            continue
        
        if user_input == "/fork":
            import uuid
            fork_id = str(uuid.uuid4())[:8]
            work_dir = get_work_dir()
            fork_path = work_dir / ".agent_data" / "forks" / f"fork_{fork_id}.json"
            agent.memory.save_to_file(fork_path)
            console.print(f"[green]🌿 会话分支已创建: {fork_id}[/green]")
            console.print(f"[dim]使用 /resume {fork_id} 恢复此分支[/dim]")
            continue
        
        if user_input == "/forks":
            work_dir = get_work_dir()
            forks_dir = work_dir / ".agent_data" / "forks"
            fork_files = list(forks_dir.glob("fork_*.json")) if forks_dir.exists() else []
            
            if not fork_files:
                console.print("[yellow]暂无会话分支，使用 /fork 创建分支[/yellow]")
            else:
                console.print(f"[yellow]🌿 会话分支列表 ({len(fork_files)} 个):[/yellow]")
                for fork_file in sorted(fork_files, key=lambda x: x.stat().st_mtime, reverse=True):
                    fork_id = fork_file.stem.replace("fork_", "")
                    mtime = fork_file.stat().st_mtime
                    create_time = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        with open(fork_file, "r", encoding="utf-8") as f:
                            fork_data = json.load(f)
                            msg_count = len(fork_data.get("messages", []))
                    except:
                        msg_count = "?"
                    console.print(f"  📌 [cyan]{fork_id}[/cyan] | 创建时间: {create_time} | 消息数: {msg_count}")
                console.print("[dim]使用 /resume <id> 恢复指定分支[/dim]")
            continue
        
        if user_input.startswith("/resume "):
            fork_id = user_input[8:].strip()
            work_dir = get_work_dir()
            fork_path = work_dir / ".agent_data" / "forks" / f"fork_{fork_id}.json"
            if fork_path.exists():
                if agent.memory.load_from_file(fork_path):
                    print_success(f"已恢复分支: {fork_id}")
                else:
                    print_error("恢复失败", f"无法加载分支 {fork_id}")
            else:
                print_error("分支不存在", f"找不到分支 {fork_id}")
            continue
        
        if user_input == "/pwd":
            console.print(f"[yellow]📁 当前工作目录: {get_work_dir()}[/yellow]")
            continue
        
        if user_input in ["/thinking", "/th"]:
            agent.set_thinking_mode(True)
            console.print(f"[magenta]🧠 思考模式已开启 - 模型将先进行推理再回答[/magenta]")
            continue
        
        if user_input in ["/unthinking", "/unth"]:
            agent.set_thinking_mode(False)
            console.print(f"[yellow]💭 思考模式已关闭 - 恢复默认模式[/yellow]")
            continue
        
        if user_input == "/analyze":
            result = agent.analyze_project()
            console.print(f"[yellow]📊 项目结构分析:[/yellow]")
            console.print(result)
            continue
        
        if user_input == "/history":
            history = agent.get_history()
            console.print(f"[yellow]📜 变更历史:[/yellow]")
            console.print(history)
            continue
        
        if user_input == "/undo":
            if not agent.can_undo():
                console.print("[yellow]⚠️ 没有可撤销的变更[/yellow]")
            else:
                result = agent.undo_last_change()
                console.print(f"[yellow]↩️ {result}[/yellow]")
            continue
        
        if user_input == "/redo":
            if not agent.can_redo():
                console.print("[yellow]⚠️ 没有可重做的变更[/yellow]")
            else:
                result = agent.redo_last_change()
                console.print(f"[yellow]↪️ {result}[/yellow]")
            continue
        
        if user_input in ["/continue", "/c"]:
            if agent.has_pending_followup():
                console.print("[yellow]⏳ 继续执行任务...[/yellow]")
                console.print("[bold green]🤖 Assistant:[/bold green]", end="")
                response = agent.continue_task()
            else:
                print_info("没有待继续的任务")
            continue
        
        if user_input == "/status":
            status = agent.get_followup_status()
            console.print(f"[yellow]📊 任务状态:[/yellow]")
            console.print(status)
            continue
        
        if user_input == "/stop":
            agent.stop_task()
            print_warning("任务已停止")
            continue
        
        if user_input.startswith("/cd "):
            new_dir = user_input[4:].strip()
            try:
                new_path = Path(new_dir)
                if not new_path.is_absolute():
                    new_path = get_work_dir() / new_path
                if new_path.exists() and new_path.is_dir():
                    set_work_dir(new_path)
                    console.print(f"[yellow]📁 工作目录已切换: {get_work_dir()}[/yellow]")
                else:
                    print_error("目录不存在", str(new_path))
            except Exception as e:
                print_error("切换失败", str(e))
            continue
        
        if user_input == "/jobs":
            from tools.shell_tools import process_manager
            processes = process_manager.list_processes()
            if not processes:
                console.print("[yellow]📭 没有后台进程[/yellow]")
            else:
                console.print("[yellow]📋 后台进程列表:[/yellow]")
                for proc in processes:
                    status_icon = "🟢" if proc.is_running() else "🔴"
                    elapsed = (datetime.now() - proc.start_time).total_seconds()
                    console.print(f"  {status_icon} [{proc.id}] {proc.command}")
                    console.print(f"     状态: {proc.status} | 运行时间: {elapsed:.0f}秒")
            continue
        
        if user_input == "/cleanup":
            from tools.shell_tools import process_manager
            removed_count = process_manager.cleanup_old_processes()
            if removed_count > 0:
                console.print(f"[green]🧹 已清理 {removed_count} 个过期进程记录[/green]")
            else:
                console.print("[yellow]🧹 没有需要清理的过期进程[/yellow]")
            continue
        
        if user_input.startswith("/kill "):
            from tools.shell_tools import process_manager
            process_id = user_input[6:].strip()
            if process_manager.terminate_process(process_id):
                console.print(f"[green]✅ 进程 {process_id} 已终止[/green]")
            else:
                console.print(f"[red]❌ 无法终止进程 {process_id}（可能不存在或已结束）[/red]")
            continue
        
        if user_input.startswith("/logs "):
            from tools.shell_tools import process_manager
            process_id = user_input[6:].strip()
            proc = process_manager.get_process(process_id)
            if proc:
                output = proc.get_output(100)
                console.print(f"[yellow]📄 进程 {process_id} 输出:[/yellow]")
                console.print(output if output else "(无输出)")
            else:
                console.print(f"[red]❌ 进程 {process_id} 不存在[/red]")
            continue
        
        if user_input == "/todos":
            from tools.todo_tool import TodoWriteTool
            todos = TodoWriteTool.load_todos()
            if not todos:
                console.print("[yellow]📋 当前没有任务列表[/yellow]")
                console.print("[dim]提示: 让 AI 处理复杂任务时会自动创建任务列表[/dim]")
            else:
                status_icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}
                priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                
                console.print(f"\n[bold yellow]📋 任务列表[/bold yellow]")
                completed = 0
                for todo in todos:
                    status = todo.get("status", "pending")
                    priority = todo.get("priority", "medium")
                    content = todo.get("content", "")
                    status_icon = status_icons.get(status, "❓")
                    priority_icon = priority_icons.get(priority, "🟡")
                    console.print(f"  {status_icon} {priority_icon} {content}")
                    if status == "completed":
                        completed += 1
                
                total = len(todos)
                percent = completed / total * 100 if total > 0 else 0
                console.print(f"\n[dim]📊 进度: {completed}/{total} 完成 ({percent:.0f}%)[/dim]")
            continue
        
        console.print("[bold green]🤖 Assistant:[/bold green]", end="")
        
        start_time = time.time()
        
        try:
            response = agent.run(user_input)
            
            elapsed = time.time() - start_time
            
            input_tokens = getattr(agent, '_last_input_tokens', 0)
            output_tokens = getattr(agent, '_last_output_tokens', 0)
            if input_tokens > 0 or output_tokens > 0:
                session_stats.add_tokens(input_tokens, output_tokens)
                print_stats(input_tokens, output_tokens, elapsed)
            
            agent.check_and_compress()
            
            if len(agent.memory.messages) > 0 and len(agent.memory.messages) % 5 == 0:
                agent.save_session()
            
            if agent.has_pending_followup():
                console.print(f"\n[yellow]💡 提示: 输入 /continue 继续执行任务[/yellow]")
        except KeyboardInterrupt:
            console.print("\n[red]⚠️ 操作已中断[/red]")
            continue
        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            print_error("处理请求失败", str(e))

if __name__ == "__main__":
    main()
