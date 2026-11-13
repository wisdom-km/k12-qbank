"""Shared primitives only. No business rules and no framework imports."""

from backend.kernel.log_event import LogEvent
from backend.kernel.logger import Logger
from backend.kernel.result import Err, Ok

__all__ = ["Err", "LogEvent", "Logger", "Ok"]
