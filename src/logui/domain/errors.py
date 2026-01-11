class DomainError(Exception):
    """Base class for domain-related errors."""


class ValidationError(DomainError):
    """Raised when an entity violates domain invariants."""
