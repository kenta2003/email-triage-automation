from __future__ import annotations

from abc import ABC, abstractmethod

from processor import SourceItem


class BaseSource(ABC):
    @abstractmethod
    def fetch(self) -> list[SourceItem]:
        raise NotImplementedError

    @abstractmethod
    def mark_processed(self, items: list[SourceItem]) -> None:
        raise NotImplementedError

