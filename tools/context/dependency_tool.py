import re
from pathlib import Path
from typing import Dict, Any, List, Set
from collections import defaultdict
from ..base import Tool
from config import get_work_dir


class DependencyTool(Tool):
    @property
    def name(self) -> str:
        return "dependency"

    @property
    def description(self) -> str:
        return "分析项目文件的依赖关系。解析 import 语句，生成依赖关系图，检测循环依赖。支持 Python 和 JavaScript/TypeScript 文件。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要分析的项目路径，默认为当前工作目录"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件类型过滤模式，默认为 '*.py'。支持如 '*.py', '*.ts', '*.js' 等"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["text", "mermaid"],
                    "description": "输出格式，支持 'text'（文本格式）和 'mermaid'（Mermaid 图表格式），默认为 'text'"
                }
            },
            "required": []
        }

    def execute(self, path: str = None, file_pattern: str = "*.py", output_format: str = "text", **kwargs) -> str:
        try:
            target_path = self._resolve_path(path) if path else get_work_dir()

            if not target_path.exists():
                return f"错误：路径不存在: {target_path}"

            if not target_path.is_dir():
                return f"错误：路径不是目录: {target_path}"

            dependencies = self._analyze_dependencies(target_path, file_pattern)

            if not dependencies:
                return f"未找到匹配 '{file_pattern}' 的文件或未发现依赖关系: {target_path}"

            circular_deps = self._detect_circular_dependencies(dependencies)

            if output_format == "mermaid":
                return self._generate_mermaid_output(dependencies, circular_deps)
            else:
                return self._generate_text_output(dependencies, circular_deps, target_path)

        except Exception as e:
            return f"依赖分析失败: {str(e)}"

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p

    def _analyze_dependencies(self, root_path: Path, file_pattern: str) -> Dict[str, Set[str]]:
        dependencies = defaultdict(set)
        patterns = self._get_patterns_for_file_type(file_pattern)

        for file_path in root_path.rglob(file_pattern):
            if self._should_skip_file(file_path):
                continue

            relative_path = str(file_path.relative_to(root_path))
            imports = self._extract_imports(file_path, patterns)

            if imports:
                dependencies[relative_path] = imports

        return dict(dependencies)

    def _get_patterns_for_file_type(self, file_pattern: str) -> Dict[str, re.Pattern]:
        if file_pattern.endswith('.py'):
            return {
                'import': re.compile(r'^import\s+([^\s#]+)', re.MULTILINE),
                'from_import': re.compile(r'^from\s+([^\s]+)\s+import', re.MULTILINE),
            }
        elif file_pattern.endswith('.js') or file_pattern.endswith('.ts') or file_pattern.endswith('.tsx'):
            return {
                'import': re.compile(r'^import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE),
                'require': re.compile(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', re.MULTILINE),
                'export_from': re.compile(r'^export\s+.*?from\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE),
            }
        return {}

    def _should_skip_file(self, file_path: Path) -> bool:
        skip_dirs = {'node_modules', '__pycache__', '.git', 'venv', 'env', '.venv', 'dist', 'build'}
        return any(part in skip_dirs for part in file_path.parts)

    def _extract_imports(self, file_path: Path, patterns: Dict[str, re.Pattern]) -> Set[str]:
        imports = set()

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            for pattern_name, pattern in patterns.items():
                matches = pattern.findall(content)
                for match in matches:
                    module_name = match.strip()
                    if module_name:
                        imports.add(module_name)

        except Exception:
            pass

        return imports

    def _detect_circular_dependencies(self, dependencies: Dict[str, Set[str]]) -> List[List[str]]:
        circular_deps = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor) if neighbor in path else len(path)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in circular_deps:
                        circular_deps.append(cycle)

            rec_stack.remove(node)

        for node in dependencies:
            if node not in visited:
                dfs(node, [node])

        return circular_deps

    def _generate_text_output(self, dependencies: Dict[str, Set[str]], circular_deps: List[List[str]], root_path: Path) -> str:
        lines = []
        lines.append(f"依赖关系分析报告")
        lines.append(f"项目路径: {root_path}")
        lines.append(f"分析文件数: {len(dependencies)}")
        lines.append("=" * 60)

        lines.append("\n文件依赖详情:")
        lines.append("-" * 60)

        for file_path, imports in sorted(dependencies.items()):
            lines.append(f"\n{file_path}:")
            if imports:
                for imp in sorted(imports):
                    lines.append(f"  -> {imp}")
            else:
                lines.append("  (无外部依赖)")

        lines.append("\n" + "=" * 60)
        lines.append("\n循环依赖检测:")

        if circular_deps:
            lines.append(f"发现 {len(circular_deps)} 个循环依赖:")
            for i, cycle in enumerate(circular_deps, 1):
                lines.append(f"  {i}. {' -> '.join(cycle)}")
        else:
            lines.append("未检测到循环依赖")

        return "\n".join(lines)

    def _generate_mermaid_output(self, dependencies: Dict[str, Set[str]], circular_deps: List[List[str]]) -> str:
        lines = []
        lines.append("```mermaid")
        lines.append("graph TD")

        node_map = {}
        node_counter = 0

        def get_node_id(name: str) -> str:
            nonlocal node_counter
            if name not in node_map:
                node_map[name] = f"N{node_counter}"
                node_counter += 1
            return node_map[name]

        for file_path, imports in dependencies.items():
            file_id = get_node_id(file_path)
            safe_name = file_path.replace('"', "'")
            lines.append(f'    {file_id}["{safe_name}"]')

            for imp in imports:
                imp_id = get_node_id(imp)
                safe_imp = imp.replace('"', "'")
                lines.append(f'    {imp_id}["{safe_imp}"]')
                lines.append(f'    {file_id} --> {imp_id}')

        if circular_deps:
            lines.append("")
            lines.append("    %% 循环依赖标记")
            lines.append("    classDef circular fill:#ff6b6b,stroke:#c92a2a,color:#fff")

            for cycle in circular_deps:
                for node in cycle:
                    if node in node_map:
                        lines.append(f'    class {node_map[node]} circular')

        lines.append("```")

        if circular_deps:
            lines.append("")
            lines.append("**检测到循环依赖:**")
            for i, cycle in enumerate(circular_deps, 1):
                lines.append(f"{i}. {' -> '.join(cycle)}")

        return "\n".join(lines)
