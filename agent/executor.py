from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.base import Tool
from utils.exceptions import ToolNotFoundException, ToolExecutionException
from utils.logger import get_logger
from mcp.adapter import MCPToolAdapter
import json
from .subagents.base import ToolPermission

logger = get_logger()

class ToolExecutor:
    def __init__(self, tools: Optional[Dict[str, Tool]] = None, max_workers: int = 5):
        self.tools: Dict[str, Tool] = tools or {}
        self.mcp_tools: Dict[str, MCPToolAdapter] = {}
        self.max_workers = max_workers
        self._permission: Optional[ToolPermission] = None

    def set_permission(self, permission: Optional[ToolPermission]) -> None:
        self._permission = permission
    
    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def register_tools(self, tools: List[Tool]) -> None:
        for tool in tools:
            self.register_tool(tool)
    
    def register_mcp_tools(self, mcp_tools: List[MCPToolAdapter]) -> None:
        for mcp_tool in mcp_tools:
            self.mcp_tools[mcp_tool.name] = mcp_tool
            logger.info(f"注册MCP工具: {mcp_tool.name}")
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        if self._permission is None:
            definitions = [tool.to_openai_tool() for tool in self.tools.values()]
            definitions.extend([mcp_tool.to_openai_tool() for mcp_tool in self.mcp_tools.values()])
            return definitions

        definitions: List[Dict[str, Any]] = []
        for tool in self.tools.values():
            if self._check_permission(tool.name):
                definitions.append(tool.to_openai_tool())
        for mcp_tool in self.mcp_tools.values():
            if self._check_permission(mcp_tool.name):
                definitions.append(mcp_tool.to_openai_tool())
        return definitions
    
    def execute(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(tool_calls) <= 1:
            return self._execute_sequential(tool_calls)
        
        return self._execute_parallel(tool_calls)
    
    def _execute_sequential(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        
        for tool_call in tool_calls:
            result = self._execute_single_tool_call(tool_call)
            results.append(result)
        
        return results
    
    def _execute_parallel(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = [None] * len(tool_calls)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_index = {}
            
            for index, tool_call in enumerate(tool_calls):
                future = executor.submit(self._execute_single_tool_call, tool_call)
                future_to_index[future] = index
            
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    tool_call = tool_calls[index]
                    tool_name = tool_call.get("function", {}).get("name", "unknown")
                    error_msg = f"工具执行异常: {str(e)}"
                    logger.error(error_msg)
                    results[index] = {
                        "tool_call_id": tool_call.get("id", ""),
                        "role": "tool",
                        "content": error_msg
                    }
        
        return results
    
    def _execute_single_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        tool_call_id = tool_call.get("id", "")
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments_str = function.get("arguments", "{}")
        
        if not tool_name:
            error_msg = "工具调用缺少工具名称"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"错误: {error_msg}"
            }
        
        try:
            arguments = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError as e:
            error_msg = f"工具参数 JSON 解析失败: {str(e)}"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"错误: {error_msg}, 原始参数: {arguments_str}"
            }
        
        logger.info(f"执行工具: {tool_name}, 参数: {arguments}")
        
        try:
            result = self._execute_single_tool(tool_name, **arguments)
            logger.info(f"工具执行成功: {tool_name}")
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": result
            }
        except ToolNotFoundException as e:
            error_msg = f"工具未找到: {tool_name}"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": error_msg
            }
        except ToolExecutionException as e:
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": error_msg
            }
        except TypeError as e:
            error_msg = f"工具参数错误: {str(e)}"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": error_msg
            }
        except Exception as e:
            error_msg = f"工具执行异常: {str(e)}"
            logger.error(error_msg)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": error_msg
            }
    
    def _execute_single_tool(self, tool_name: str, **kwargs) -> str:
        if not self._check_permission(tool_name):
            return f"错误：无权限使用工具 '{tool_name}'"

        if tool_name in self.mcp_tools:
            mcp_tool = self.mcp_tools[tool_name]
            try:
                result = mcp_tool.execute(**kwargs)
                return result
            except Exception as e:
                raise ToolExecutionException(f"执行MCP工具 '{tool_name}' 时发生错误: {str(e)}")
        
        if tool_name not in self.tools:
            raise ToolNotFoundException(f"工具 '{tool_name}' 未注册")
        
        tool = self.tools[tool_name]
        
        try:
            result = tool.execute(**kwargs)
            return result
        except Exception as e:
            raise ToolExecutionException(f"执行工具 '{tool_name}' 时发生错误: {str(e)}")

    def _check_permission(self, tool_name: str) -> bool:
        permission = self._permission
        if permission is None:
            return True

        restricted = set(permission.restricted_tools or [])
        if tool_name in restricted:
            logger.debug(f"权限检查: {tool_name} 在 restricted_tools 中")
            return False

        allowed = permission.allowed_tools
        if allowed is None:
            return True

        allowed_set = set(allowed)
        result = tool_name in allowed_set
        if not result:
            logger.debug(f"权限检查: {tool_name} 不在 allowed_tools 中。allowed_tools={allowed}")
        return result
    
    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools or tool_name in self.mcp_tools
    
    def list_tools(self) -> List[str]:
        return list(self.tools.keys()) + list(self.mcp_tools.keys())
