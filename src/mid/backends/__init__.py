"""Backends package — re-exports."""

from mid.backends.base import Availability, Backend
from mid.backends.registry import BackendRegistry, registry
from mid.backends.detection import which_tool, run_version
from mid.backends.adapter import BackendAdapter

try:
    from mid.backends.libreoffice import LibreOfficeBackend

    registry.register(LibreOfficeBackend())
except ValueError:
    pass
except Exception:
    pass

__all__ = ["Availability", "Backend", "BackendRegistry", "registry", "which_tool", "run_version", "BackendAdapter"]
