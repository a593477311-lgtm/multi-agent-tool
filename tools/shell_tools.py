import subprocess
import shlex
import threading
import time
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from .base import Tool
from config import get_work_dir

ALLOWED_COMMANDS = {
    "ls", "dir", "pwd", "cd", "echo", "cat", "type",
    "mkdir", "git", "python", "pip", "npm", "node",
    "curl", "wget", "ping",
}

BLOCKED_PATTERNS = [
    "rm -rf /",
    "del /",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
    "dd if=",
    "> /dev/",
    "chmod 777",
    "rm ",
    "del ",
    "rmdir",
    "rd ",
    "Remove-Item",
]

DELETE_COMMAND_SUGGESTION = "删除操作请使用 file_delete 工具，该工具提供安全的删除功能并需要用户确认。"

LONG_RUNNING_PATTERNS = [
    "python app.py",
    "python run.py",
    "python main.py",
    "python server.py",
    "flask run",
    "uvicorn",
    "gunicorn",
    "npm run dev",
    "npm start",
    "yarn dev",
    "yarn start",
    "node server.js",
    "node app.js",
    "python -m http.server",
    "php -S",
    "ruby -run",
    "go run",
    "cargo run",
]

@dataclass
class BackgroundProcess:
    id: str
    command: str
    process: subprocess.Popen
    start_time: datetime
    work_dir: str
    output_file: str
    status: str = "running"
    end_time: Optional[datetime] = None
    
    def get_output(self, lines: int = 50) -> str:
        try:
            if os.path.exists(self.output_file):
                with open(self.output_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    all_lines = content.split("\n")
                    return "\n".join(all_lines[-lines:])
            return ""
        except:
            return ""
    
    def is_running(self) -> bool:
        if self.process.poll() is None:
            return True
        if self.end_time is None:
            self.end_time = datetime.now()
            self.status = "finished"
        return False
    
    def terminate(self) -> bool:
        try:
            if self.is_running():
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.status = "terminated"
                if self.end_time is None:
                    self.end_time = datetime.now()
                return True
            return False
        except:
            return False

class ProcessManager:
    _instance = None
    _processes: Dict[str, BackgroundProcess] = {}
    _counter = 0
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def create_process(self, command: str, work_dir: str) -> BackgroundProcess:
        self._counter += 1
        process_id = f"bg_{self._counter:03d}"
        
        output_dir = os.path.join(work_dir, ".agent_data", "logs")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{process_id}.log")
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=open(output_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            cwd=work_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )
        
        bg_process = BackgroundProcess(
            id=process_id,
            command=command,
            process=process,
            start_time=datetime.now(),
            work_dir=work_dir,
            output_file=output_file
        )
        
        self._processes[process_id] = bg_process
        return bg_process
    
    def get_process(self, process_id: str) -> Optional[BackgroundProcess]:
        return self._processes.get(process_id)
    
    def list_processes(self) -> List[BackgroundProcess]:
        self.cleanup_old_processes()
        return list(self._processes.values())
    
    def terminate_process(self, process_id: str) -> bool:
        process = self._processes.get(process_id)
        if process:
            return process.terminate()
        return False
    
    def cleanup_finished(self) -> int:
        finished = []
        for pid, proc in self._processes.items():
            if not proc.is_running():
                proc.status = "finished"
                finished.append(pid)
        return len(finished)
    
    def cleanup_old_processes(self, max_age_hours: int = 1) -> int:
        removed = []
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        for pid, proc in list(self._processes.items()):
            proc.is_running()
            if proc.end_time is not None and proc.end_time < cutoff_time:
                removed.append(pid)
                del self._processes[pid]
        return len(removed)

process_manager = ProcessManager()

class ShellCommandTool(Tool):
    @property
    def name(self) -> str:
        return "shell_command"
    
    @property
    def description(self) -> str:
        return """执行Shell命令。【必需参数】command：要执行的命令（字符串）。
【可选参数】background：是否后台执行（布尔值，默认自动检测）。
示例：{"command": "ls -la"} 或 {"command": "python app.py", "background": true}
命令在工作区目录下执行。长时间运行的命令（如启动服务器）会自动后台执行。"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的Shell命令（必需）。例如：'ls -la' 或 'python main.py'"
                },
                "background": {
                    "type": "boolean",
                    "description": "是否后台执行（可选，默认自动检测长时间运行的命令）"
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str = None, background: bool = None, **kwargs) -> str:
        if command is None or command == "":
            return "错误：缺少必需参数 'command'。请提供要执行的命令。示例：shell_command(command=\"ls -la\")"
        
        try:
            if not self._is_command_safe(command):
                if self._is_delete_command(command):
                    return f"错误：删除命令被禁止执行。\n{DELETE_COMMAND_SUGGESTION}\n命令: {command}"
                return f"错误：命令被禁止执行（安全限制）: {command}"
            
            work_dir = str(get_work_dir())
            
            if background is None:
                background = self._is_long_running(command)
            
            if background:
                return self._execute_background(command, work_dir)
            else:
                return self._execute_foreground(command, work_dir)
                
        except Exception as e:
            return f"执行命令失败: {str(e)}"
    
    def _execute_foreground(self, command: str, work_dir: str) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=work_dir
            )
            
            output = []
            if result.stdout:
                output.append(f"标准输出:\n{result.stdout}")
            if result.stderr:
                output.append(f"标准错误:\n{result.stderr}")
            
            output.append(f"退出码: {result.returncode}")
            
            return "\n".join(output) if output else "命令执行完成，无输出"
        except subprocess.TimeoutExpired:
            return "错误：命令执行超时（60秒）。如果是长时间运行的命令，请使用 background=true 参数后台执行。"
    
    def _execute_background(self, command: str, work_dir: str) -> str:
        bg_process = process_manager.create_process(command, work_dir)
        
        time.sleep(0.5)
        
        initial_output = bg_process.get_output(10)
        
        result = f"""✅ 后台进程已启动
📌 进程ID: {bg_process.id}
📝 命令: {command}
📁 工作目录: {work_dir}
⏰ 启动时间: {bg_process.start_time.strftime('%H:%M:%S')}

初始输出:
{initial_output if initial_output else '(等待输出...)'}

💡 提示:
- 使用 /jobs 查看所有后台进程
- 使用 /kill <进程ID> 终止进程
- 使用 /logs <进程ID> 查看进程输出"""
        
        return result
    
    def _is_long_running(self, command: str) -> bool:
        command_lower = command.lower()
        for pattern in LONG_RUNNING_PATTERNS:
            if pattern.lower() in command_lower:
                return True
        return False
    
    def _is_delete_command(self, command: str) -> bool:
        delete_patterns = ["rm ", "del ", "rmdir", "rd ", "Remove-Item"]
        command_lower = command.lower()
        for pattern in delete_patterns:
            if pattern.lower() in command_lower:
                return True
        return False
    
    def _is_command_safe(self, command: str) -> bool:
        command_lower = command.lower()
        
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in command_lower:
                return False
        
        return True
