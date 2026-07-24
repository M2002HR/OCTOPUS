class AgentError(Exception):
    """Base class for errors that can be reported safely to an operator."""


class ConfigurationError(AgentError):
    pass


class AjilUnavailableError(AgentError):
    pass


class AjilFallbackError(AgentError):
    pass


class StructuredOutputError(AgentError):
    pass


class CodexStartupError(AgentError):
    pass


class CodexProtocolError(AgentError):
    pass


class CodexTurnError(AgentError):
    pass


class CodexApprovalError(AgentError):
    pass


class JobCancelledError(AgentError):
    pass


class JobTimeoutError(AgentError):
    pass


class ToolExecutionError(AgentError):
    pass


class BrowserVerificationError(AgentError):
    pass


class ArtifactError(AgentError):
    pass


class MemoryError(AgentError):
    pass
