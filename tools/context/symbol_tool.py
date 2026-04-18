import ast
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tools.base import Tool
from config import get_work_dir


class SymbolTool(Tool):
    @property
    def name(self) -> str:
        return "symbol"
    
    @property
    def description(self) -> str:
        return "符号查找工具。支持列出文件或目录中的符号（函数、类、变量），查找符号定义位置，以及查找符号引用位置。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "find", "refs"],
                    "description": "操作类型：list-列出符号，find-查找符号定义，refs-查找符号引用"
                },
                "path": {
                    "type": "string",
                    "description": "文件或目录路径（可选，默认为工作目录）"
                },
                "name": {
                    "type": "string",
                    "description": "符号名称（用于 find 和 refs 操作）"
                },
                "symbol_type": {
                    "type": "string",
                    "enum": ["function", "class", "variable"],
                    "description": "符号类型过滤（可选）"
                }
            },
            "required": ["action"]
        }
    
    def execute(self, action: str, path: str = None, name: str = None, symbol_type: str = None, **kwargs) -> str:
        try:
            if action == "list":
                return self._list_symbols(path, symbol_type)
            elif action == "find":
                if not name:
                    return "错误：find 操作需要提供 name 参数"
                return self._find_symbol(name, path, symbol_type)
            elif action == "refs":
                if not name:
                    return "错误：refs 操作需要提供 name 参数"
                return self._find_references(name, path)
            else:
                return f"错误：未知的操作类型: {action}"
        except Exception as e:
            return f"符号查找失败: {str(e)}"
    
    def _resolve_path(self, path: str = None) -> Path:
        if path is None:
            return get_work_dir()
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p
    
    def _get_python_files(self, path: Path) -> List[Path]:
        if path.is_file():
            if path.suffix == ".py":
                return [path]
            return []
        
        python_files = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for file in files:
                if file.endswith(".py"):
                    python_files.append(Path(root) / file)
        return python_files
    
    def _extract_symbols(self, file_path: Path) -> List[Dict[str, Any]]:
        symbols = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    symbols.append({
                        "name": node.name,
                        "type": "function",
                        "file": str(file_path),
                        "line": node.lineno,
                        "end_line": node.end_lineno,
                        "docstring": ast.get_docstring(node) or ""
                    })
                elif isinstance(node, ast.ClassDef):
                    symbols.append({
                        "name": node.name,
                        "type": "class",
                        "file": str(file_path),
                        "line": node.lineno,
                        "end_line": node.end_lineno,
                        "docstring": ast.get_docstring(node) or ""
                    })
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            symbols.append({
                                "name": target.id,
                                "type": "variable",
                                "file": str(file_path),
                                "line": node.lineno,
                                "end_line": node.end_lineno,
                                "docstring": ""
                            })
                        elif isinstance(target, ast.Tuple):
                            for elt in target.elts:
                                if isinstance(elt, ast.Name):
                                    symbols.append({
                                        "name": elt.id,
                                        "type": "variable",
                                        "file": str(file_path),
                                        "line": node.lineno,
                                        "end_line": node.end_lineno,
                                        "docstring": ""
                                    })
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        symbols.append({
                            "name": node.target.id,
                            "type": "variable",
                            "file": str(file_path),
                            "line": node.lineno,
                            "end_line": node.end_lineno,
                            "docstring": ""
                        })
        except SyntaxError:
            pass
        except Exception:
            pass
        
        return symbols
    
    def _find_name_references(self, tree: ast.AST, name: str) -> List[int]:
        references = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name:
                references.append(node.lineno)
            elif isinstance(node, ast.Attribute) and node.attr == name:
                references.append(node.lineno)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == name:
                    references.append(node.lineno)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == name:
                    references.append(node.lineno)
        return references
    
    def _list_symbols(self, path: str = None, symbol_type: str = None) -> str:
        target_path = self._resolve_path(path)
        
        if not target_path.exists():
            return f"错误：路径不存在: {target_path}"
        
        python_files = self._get_python_files(target_path)
        
        if not python_files:
            return f"未找到 Python 文件: {target_path}"
        
        all_symbols = []
        for file_path in python_files:
            symbols = self._extract_symbols(file_path)
            all_symbols.extend(symbols)
        
        if symbol_type:
            all_symbols = [s for s in all_symbols if s["type"] == symbol_type]
        
        if not all_symbols:
            return "未找到任何符号"
        
        result_lines = [f"找到 {len(all_symbols)} 个符号:\n"]
        
        type_icons = {"function": "fn", "class": "cl", "variable": "var"}
        
        for symbol in sorted(all_symbols, key=lambda x: (x["file"], x["line"])):
            icon = type_icons.get(symbol["type"], "?")
            relative_path = self._get_relative_path(symbol["file"])
            result_lines.append(f"  [{icon}] {symbol['name']} ({symbol['type']}) @ {relative_path}:{symbol['line']}")
            if symbol["docstring"]:
                docstring_preview = symbol["docstring"][:50] + "..." if len(symbol["docstring"]) > 50 else symbol["docstring"]
                result_lines.append(f"      {docstring_preview}")
        
        return "\n".join(result_lines)
    
    def _find_symbol(self, name: str, path: str = None, symbol_type: str = None) -> str:
        target_path = self._resolve_path(path)
        
        if not target_path.exists():
            return f"错误：路径不存在: {target_path}"
        
        python_files = self._get_python_files(target_path)
        
        all_symbols = []
        for file_path in python_files:
            symbols = self._extract_symbols(file_path)
            all_symbols.extend(symbols)
        
        matched = [s for s in all_symbols if s["name"] == name]
        
        if symbol_type:
            matched = [s for s in matched if s["type"] == symbol_type]
        
        if not matched:
            return f"未找到符号: {name}"
        
        result_lines = [f"找到 {len(matched)} 个定义:\n"]
        
        type_icons = {"function": "fn", "class": "cl", "variable": "var"}
        
        for symbol in matched:
            icon = type_icons.get(symbol["type"], "?")
            relative_path = self._get_relative_path(symbol["file"])
            result_lines.append(f"  [{icon}] {symbol['name']} ({symbol['type']}) @ {relative_path}:{symbol['line']}")
            if symbol["docstring"]:
                docstring_preview = symbol["docstring"][:100] + "..." if len(symbol["docstring"]) > 100 else symbol["docstring"]
                result_lines.append(f"      文档: {docstring_preview}")
        
        return "\n".join(result_lines)
    
    def _find_references(self, name: str, path: str = None) -> str:
        target_path = self._resolve_path(path)
        
        if not target_path.exists():
            return f"错误：路径不存在: {target_path}"
        
        python_files = self._get_python_files(target_path)
        
        references = []
        
        for file_path in python_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                tree = ast.parse(content, filename=str(file_path))
                
                file_refs = self._find_name_references(tree, name)
                
                for line_no in file_refs:
                    lines = content.split("\n")
                    if 0 < line_no <= len(lines):
                        line_content = lines[line_no - 1].strip()
                        references.append({
                            "file": str(file_path),
                            "line": line_no,
                            "content": line_content
                        })
            except SyntaxError:
                pass
            except Exception:
                pass
        
        if not references:
            return f"未找到符号引用: {name}"
        
        result_lines = [f"找到 {len(references)} 个引用:\n"]
        
        for ref in sorted(references, key=lambda x: (x["file"], x["line"])):
            relative_path = self._get_relative_path(ref["file"])
            result_lines.append(f"  {relative_path}:{ref['line']}")
            result_lines.append(f"    {ref['content']}")
        
        return "\n".join(result_lines)
    
    def _get_relative_path(self, file_path: str) -> str:
        try:
            work_dir = get_work_dir()
            path = Path(file_path)
            if str(path).startswith(str(work_dir)):
                return str(path.relative_to(work_dir))
        except Exception:
            pass
        return file_path
