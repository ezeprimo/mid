"""Custom exceptions for mid."""


class MidError(Exception):
    """Base exception for mid."""


class ConversionError(MidError):
    """Raised when document conversion fails."""


class ArgumentError(MidError):
    """Raised on invalid CLI arguments."""


class UnsupportedFormatError(MidError):
    """Raised when file format is not supported."""
