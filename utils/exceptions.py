class AgentException(Exception):
    pass

class LLMException(AgentException):
    pass

class ToolException(AgentException):
    pass

class ToolNotFoundException(ToolException):
    pass

class ToolExecutionException(ToolException):
    pass

class MemoryException(AgentException):
    pass

class ConfigurationException(AgentException):
    pass

class APIKeyMissingException(ConfigurationException):
    pass

class RateLimitException(LLMException):
    pass

class ContextLengthExceededException(LLMException):
    pass
