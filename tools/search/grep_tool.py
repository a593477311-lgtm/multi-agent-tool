import os
import re
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Tuple
from ..base import Tool
from config import get_work_dir


class GrepTool(Tool):
    @property
    def name(self) -> str:
        return "grep"
    
    @property
    def description(self) -> str:
        return ("使用正则表达式在文件中搜索匹配内容。【必需参数】pattern：正则表达式模式（字符串）。path（可选，搜索路径，默认工作目录）、file_pattern（可选，文件类型过滤如*.py）、context_lines（可选，上下文行数，默认2）、max_results（可选，最大结果数，默认50）。支持递归搜索子目录，返回匹配的文件路径、行号、匹配内容和上下文。"
                "示例：{\"pattern\": \"function\\s+\\w+\"} 或 {\"pattern\": \"import\", \"file_pattern\": \"*.py\"}")
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式模式（必需）。例如：'function\\\\s+\\\\w+' 或 'import'"
                },
                "path": {
                    "type": "string",
                    "description": "搜索路径，默认为当前工作目录"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件类型过滤，如 *.py、*.txt 等"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "上下文行数，默认为2"
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数，默认为50"
                }
            },
            "required": ["pattern"]
        }
    
    def execute(self, pattern: str = None, path: str = None, file_pattern: str = None,
                context_lines: int = 2, max_results: int = 50, **kwargs) -> str:
        if pattern is None or pattern == "":
            return "错误：缺少必需参数 'pattern'。请提供正则表达式模式。示例：grep(pattern=\"import\")"
        try:
            search_path = self._resolve_path(path) if path else get_work_dir()
            
            if not search_path.exists():
                return f"错误：路径不存在: {search_path}"
            
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return f"错误：无效的正则表达式: {str(e)}"
            
            matches = self._search_in_path(search_path, regex, file_pattern, context_lines, max_results)
            
            if not matches:
                return f"未找到匹配项: pattern='{pattern}', path='{search_path}'"
            
            return self._format_results(matches, pattern, search_path)
        except Exception as e:
            return f"搜索失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p
    
    def _search_in_path(self, search_path: Path, regex: re.Pattern, 
                        file_pattern: str, context_lines: int, max_results: int) -> List[Dict[str, Any]]:
        matches = []
        
        if search_path.is_file():
            file_matches = self._search_in_file(search_path, regex, context_lines)
            matches.extend(file_matches)
        elif search_path.is_dir():
            for root, dirs, files in os.walk(search_path):
                for filename in files:
                    if len(matches) >= max_results:
                        break
                    
                    if file_pattern and not fnmatch.fnmatch(filename, file_pattern):
                        continue
                    
                    file_path = Path(root) / filename
                    try:
                        file_matches = self._search_in_file(file_path, regex, context_lines)
                        for match in file_matches:
                            if len(matches) >= max_results:
                                break
                            matches.append(match)
                    except (UnicodeDecodeError, PermissionError, OSError):
                        continue
                
                if len(matches) >= max_results:
                    break
        
        return matches
    
    def _search_in_file(self, file_path: Path, regex: re.Pattern, 
                        context_lines: int) -> List[Dict[str, Any]]:
        matches = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except (PermissionError, OSError):
            return matches
        
        for line_num, line in enumerate(lines, start=1):
            for match in regex.finditer(line):
                context_before = []
                context_after = []
                
                for i in range(max(0, line_num - context_lines - 1), line_num - 1):
                    context_before.append((i + 1, lines[i].rstrip('\n\r')))
                
                for i in range(line_num, min(len(lines), line_num + context_lines)):
                    context_after.append((i + 1, lines[i].rstrip('\n\r')))
                
                matches.append({
                    'file_path': str(file_path),
                    'line_number': line_num,
                    'matched_content': match.group(),
                    'full_line': line.rstrip('\n\r'),
                    'start_pos': match.start(),
                    'end_pos': match.end(),
                    'context_before': context_before,
                    'context_after': context_after
                })
        
        return matches
    
    def _format_results(self, matches: List[Dict[str, Any]], pattern: str, search_path: Path) -> str:
        result_lines = [f"搜索结果 (pattern='{pattern}', path='{search_path}'):"]

        for match in matches:
            result_lines.append(f"\n{'='*60}")
            result_lines.append(f"文件: {match['file_path']}")
            result_lines.append(f"行号: {match['line_number']}")
            result_lines.append(f"匹配: {match['matched_content']}")
            result_lines.append("-" * 40)
            
            if match['context_before']:
                result_lines.append("上下文 (前):")
                for ctx_line_num, ctx_content in match['context_before']:
                    result_lines.append(f"  {ctx_line_num}: {ctx_content}")
            
            result_lines.append(f">>> {match['line_number']}: {match['full_line']}")
            
            if match['context_after']:
                result_lines.append("上下文 (后):")
                for ctx_line_num, ctx_content in match['context_after']:
                    result_lines.append(f"  {ctx_line_num}: {ctx_content}")
        
        result_lines.append(f"\n{'='*60}")
        result_lines.append(f"共找到 {len(matches)} 个匹配项")
        
        return "\n".join(result_lines)
