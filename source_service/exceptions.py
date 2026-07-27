class SourceError(Exception):
    """Base exception for source_service."""
    pass


class SourceConnectionError(SourceError):
    """Connection error to the source."""
    pass


class AuthenticationError(SourceError):
    """Authentication failed."""
    pass


class DocumentNotFoundError(SourceError):
    """Requested document was not found."""
    pass


class InvalidConfigurationError(SourceError):
    """Invalid source configuration."""
    pass
