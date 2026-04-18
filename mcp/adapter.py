"""
MCP工具适配器模块

将MCP工具适配为骤雨OS的Tool接口，实现统一的工具调用方式。
"""

import asyncio
import json
from typing import Dict, Any, Optional, TYPE_CHECKING

from tools.base import Tool
from utils.logger import get_logger

if TYPE_CHECKING:
    from mcp import ClientSession

logger = get_logger()


class MCPToolAdapter(Tool):
    """MCP工具适配器
    
    将MCP服务器提供的工具适配为骤雨OS的Tool接口，
    支持异步调用和结果转换。
    """
    
    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        input_schema: Dict[str, Any],
        session: "ClientSession",
        server_name: str,
    ):
        """初始化MCP工具适配器
        
        Args:
            tool_name: 工具名称
            tool_description: 工具描述
            input_schema: 输入参数的JSON Schema
            session: MCP客户端会话
            server_name: 所属MCP服务器名称
        """
        self._name = tool_name
        self._description = tool_description
        self._input_schema = input_schema
        self._session = session
        self._server_name = server_name
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    @property
    def name(self) -> str:
        """工具名称"""
        return self._name
    
    @property
    def description(self) -> str:
        """工具描述"""
        desc = self._description or f"MCP工具: {self._name}"
        return f"[MCP:{self._server_name}] {desc}"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """工具参数定义"""
        return self._input_schema
    
    @property
    def server_name(self) -> str:
        """所属MCP服务器名称"""
        return self._server_name
    
    def execute(self, **kwargs) -> str:
        """执行工具调用
        
        由于MCP SDK是异步的，此方法会处理异步调用。
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具执行结果字符串
        """
        try:
            return self._run_async(kwargs)
        except Exception as e:
            error_msg = f"MCP工具执行失败 [{self._name}]: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _run_async(self, arguments: Dict[str, Any]) -> str:
        """运行异步调用
        
        Args:
            arguments: 工具参数
            
        Returns:
            执行结果字符串
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop is not None:
            future = asyncio.ensure_future(self._execute_async(arguments))
            return asyncio.run_coroutine_threadsafe(future, loop).result()
        else:
            return asyncio.run(self._execute_async(arguments))
    
    async def _execute_async(self, arguments: Dict[str, Any]) -> str:
        """异步执行工具调用
        
        Args:
            arguments: 工具参数
            
        Returns:
            执行结果字符串
        """
        try:
            logger.debug(f"调用MCP工具: {self._name}, 参数: {arguments}")
            
            result = await self._session.call_tool(self._name, arguments)
            
            return self._format_result(result)
        except Exception as e:
            error_msg = f"MCP工具调用异常 [{self._name}]: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    
    def _format_result(self, result: Any) -> str:
        """格式化MCP工具返回结果
        
        Args:
            result: MCP工具返回的结果对象
            
        Returns:
            格式化后的结果字符串
        """
        if result is None:
            return "工具执行完成（无返回结果）"
        
        if hasattr(result, "content"):
            return self._format_content(result.content)
        
        if isinstance(result, str):
            return result
        
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        return str(result)
    
    def _format_content(self, content: Any) -> str:
        """格式化MCP内容对象
        
        Args:
            content: MCP内容对象
            
        Returns:
            格式化后的字符串
        """
        if isinstance(content, list):
            parts = []
            for item in content:
                if hasattr(item, "type"):
                    if item.type == "text":
                        parts.append(item.text if hasattr(item, "text") else str(item))
                    elif item.type == "image":
                        parts.append("[图片内容]")
                    elif item.type == "resource":
                        parts.append(f"[资源: {getattr(item, 'uri', 'unknown')}]")
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        
        if hasattr(content, "text"):
            return content.text
        
        return str(content)
    
    async def execute_async(self, **kwargs) -> str:
        """异步执行工具调用
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具执行结果字符串
        """
        return await self._execute_async(kwargs)
    
    def __repr__(self) -> str:
        return f"MCPToolAdapter(name={self._name!r}, server={self._server_name!r})"
