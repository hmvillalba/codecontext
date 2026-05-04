"""Base parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from codecontext.models import FileSummary


class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        ...

    @abstractmethod
    def parse(self, file_path: Path, root: Path) -> FileSummary:
        ...

    def _relative_path(self, file_path: Path, root: Path) -> str:
        try:
            return str(file_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            return str(file_path).replace("\\", "/")
