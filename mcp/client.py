"""
MCP客户端管理器模块

管理MCP服务器连接，自动发现工具，处理连接生命周期。
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator

from utils.logger import get_logger
from utils.exceptions import AgentException
from .config import MCPConfig, MCPServerConfig
from .adapter import MCPToolAdapter

logger = get_logger()


class MCPConnectionError(AgentException):
    """MCP连接错误"""
    pass


class MCPToolDiscoveryError(AgentException):
    """MCP工具发现错误"""
    pass


@dataclass
class MCPServerConnection:
    """MCP服务器连接状态"""
    
    name: str
    config: MCPServerConfig
    session: Optional[Any] = None
    tools: List[MCPToolAdapter] = field(default_factory=list)
    connected: bool = False
    error: Optional[str] = None


class MCPClientManager:
    """MCP客户端管理器
    
    负责管理多个MCP服务器的连接，自动发现工具，
    并提供统一的工具访问接口。
    """
    
    def __init__(self, config: Optional[MCPConfig] = None):
        """初始化MCP客户端管理器
        
        Args:
            config: MCP配置对象，可选
        """
        self._config = config or MCPConfig()
        self._connections: Dict[str, MCPServerConnection] = {}
        self._tools: Dict[str, MCPToolAdapter] = {}
        self._initialized = False
        self._mcp_available = self._check_mcp_available()
    
    def _check_mcp_available(self) -> bool:
        """检查MCP SDK是否可用"""
        try:
            import mcp
            return True
        except ImportError:
            logger.warning(
                "MCP SDK未安装，MCP功能将不可用。"
                "请使用 'pip install mcp' 安装。"
            )
            return False
    
    @property
    def config(self) -> MCPConfig:
        """获取当前配置"""
        return self._config
    
    @property
    def is_mcp_available(self) -> bool:
        """MCP SDK是否可用"""
        return self._mcp_available
    
    @property
    def connections(self) -> Dict[str, MCPServerConnection]:
        """获取所有连接状态"""
        return self._connections.copy()
    
    @property
    def tools(self) -> Dict[str, MCPToolAdapter]:
        """获取所有已发现的工具"""
        return self._tools.copy()
    
    def get_tool(self, name: str) -> Optional[MCPToolAdapter]:
        """获取指定名称的工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具适配器，不存在则返回None
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[MCPToolAdapter]:
        """获取所有工具列表"""
        return list(self._tools.values())
    
    def get_server_tools(self, server_name: str) -> List[MCPToolAdapter]:
        """获取指定服务器的所有工具
        
        Args:
            server_name: 服务器名称
            
        Returns:
            工具列表
        """
        connection = self._connections.get(server_name)
        if connection:
            return connection.tools.copy()
        return []
    
    async def initialize(self) -> None:
        """初始化管理器，连接所有已启用的服务器"""
        if self._initialized:
            logger.warning("MCP客户端管理器已初始化")
            return
        
        if not self._mcp_available:
            logger.warning("MCP SDK不可用，跳过初始化")
            return
        
        enabled_servers = self._config.get_enabled_servers()
        logger.info(f"开始初始化 {len(enabled_servers)} 个MCP服务器连接")
        
        for server_config in enabled_servers:
            try:
                await self._connect_server(server_config)
            except Exception as e:
                logger.error(f"连接MCP服务器失败 [{server_config.name}]: {e}")
                self._connections[server_config.name] = MCPServerConnection(
                    name=server_config.name,
                    config=server_config,
                    connected=False,
                    error=str(e),
                )
        
        self._initialized = True
        total_tools = len(self._tools)
        connected = sum(1 for c in self._connections.values() if c.connected)
        logger.info(f"MCP初始化完成: {connected}/{len(enabled_servers)} 个服务器已连接, {total_tools} 个工具可用")
    
    async def _connect_server(self, config: MCPServerConfig) -> None:
        """连接单个MCP服务器
        
        Args:
            config: 服务器配置
        """
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        
        logger.info(f"正在连接MCP服务器: {config.name}")
        
        env = os.environ.copy()
        env.update(config.env)
        
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=env,
        )
        
        connection = MCPServerConnection(
            name=config.name,
            config=config,
        )
        
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    connection.session = session
                    connection.connected = True
                    
                    tools = await self._discover_tools(session, config.name)
                    connection.tools = tools
                    
                    for tool in tools:
                        self._tools[tool.name] = tool
                    
                    self._connections[config.name] = connection
                    logger.info(
                        f"MCP服务器已连接: {config.name}, "
                        f"发现 {len(tools)} 个工具"
                    )
                    
        except Exception as e:
            connection.error = str(e)
            self._connections[config.name] = connection
            raise MCPConnectionError(f"连接失败: {e}")
    
    async def _discover_tools(
        self, 
        session: Any, 
        server_name: str
    ) -> List[MCPToolAdapter]:
        """发现服务器提供的工具
        
        Args:
            session: MCP会话
            server_name: 服务器名称
            
        Returns:
            工具适配器列表
        """
        tools = []
        
        try:
            tools_response = await session.list_tools()
            
            if hasattr(tools_response, 'tools'):
                tool_list = tools_response.tools
            else:
                tool_list = tools_response if isinstance(tools_response, list) else []
            
            for tool_info in tool_list:
                try:
                    adapter = MCPToolAdapter(
                        tool_name=tool_info.name,
                        tool_description=tool_info.description or "",
                        input_schema=tool_info.inputSchema or {},
                        session=session,
                        server_name=server_name,
                    )
                    tools.append(adapter)
                    logger.debug(f"发现MCP工具: {tool_info.name}")
                except Exception as e:
                    logger.error(f"创建工具适配器失败 [{tool_info.name}]: {e}")
            
        except Exception as e:
            logger.error(f"获取工具列表失败 [{server_name}]: {e}")
            raise MCPToolDiscoveryError(f"工具发现失败: {e}")
        
        return tools
    
    async def connect_server(self, config: MCPServerConfig) -> bool:
        """连接单个MCP服务器
        
        Args:
            config: 服务器配置
            
        Returns:
            是否连接成功
        """
        if not self._mcp_available:
            logger.warning("MCP SDK不可用")
            return False
        
        try:
            await self._connect_server(config)
            return True
        except Exception as e:
            logger.error(f"连接MCP服务器失败 [{config.name}]: {e}")
            return False
    
    async def disconnect_server(self, name: str) -> bool:
        """断开指定服务器连接
        
        Args:
            name: 服务器名称
            
        Returns:
            是否成功断开
        """
        connection = self._connections.get(name)
        if not connection:
            return False
        
        for tool in connection.tools:
            self._tools.pop(tool.name, None)
        
        connection.connected = False
        connection.session = None
        connection.tools = []
        
        logger.info(f"已断开MCP服务器连接: {name}")
        return True
    
    async def shutdown(self) -> None:
        """关闭所有连接"""
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)
        
        self._tools.clear()
        self._initialized = False
        logger.info("MCP客户端管理器已关闭")
    
    async def reload_config(self, config: MCPConfig) -> None:
        """重新加载配置
        
        Args:
            config: 新的配置对象
        """
        await self.shutdown()
        self._config = config
        await self.initialize()
    
    def get_connection_status(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定服务器的连接状态
        
        Args:
            name: 服务器名称
            
        Returns:
            状态信息字典
        """
        connection = self._connections.get(name)
        if not connection:
            return None
        
        return {
            "name": connection.name,
            "connected": connection.connected,
            "tool_count": len(connection.tools),
            "error": connection.error,
        }
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务器的连接状态"""
        return {
            name: self.get_connection_status(name)
            for name in self._connections
        }
    
    @asynccontextmanager
    async def managed_connection(
        self, 
        config: MCPServerConfig
    ) -> AsyncGenerator[MCPServerConnection, None]:
        """上下文管理器，自动管理连接生命周期
        
        Args:
            config: 服务器配置
            
        Yields:
            服务器连接对象
        """
        if not self._mcp_available:
            raise MCPConnectionError("MCP SDK不可用")
        
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        
        env = os.environ.copy()
        env.update(config.env)
        
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=env,
        )
        
        connection = MCPServerConnection(
            name=config.name,
            config=config,
        )
        
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    connection.session = session
                    connection.connected = True
                    
                    tools = await self._discover_tools(session, config.name)
                    connection.tools = tools
                    
                    yield connection
                    
        except Exception as e:
            connection.error = str(e)
            raise MCPConnectionError(f"连接失败: {e}")
        finally:
            connection.connected = False
            connection.session = None


def create_mcp_manager_from_config(config_path: Path) -> MCPClientManager:
    """从配置文件创建MCP客户端管理器
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        MCPClientManager实例
    """
    config = MCPConfig.from_json_file(config_path)
    return MCPClientManager(config)
