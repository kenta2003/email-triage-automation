from __future__ import annotations

from abc import ABC, abstractmethod

from processor import ClassifiedItem


class BaseNotifier(ABC):
    @abstractmethod
    def notify(self, items: list[ClassifiedItem], account_name: str) -> None:
        raise NotImplementedError

