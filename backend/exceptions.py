"""Custom exception classes for the application."""

class RocoKingdomException(Exception):
    """Base exception for all application errors."""
    pass


class ValidationError(RocoKingdomException):
    """Raised when input validation fails."""
    pass


class TeamValidationError(ValidationError):
    """Raised when team composition validation fails."""
    pass


class DatabaseError(RocoKingdomException):
    """Raised when database operations fail."""
    pass


class ExternalAPIError(RocoKingdomException):
    """Raised when external API calls (like LLM) fail."""
    pass


class ResourceNotFoundError(RocoKingdomException):
    """Raised when a requested resource is not found."""
    pass


class DuplicateResourceError(RocoKingdomException):
    """Raised when attempting to create a duplicate resource."""
    pass
