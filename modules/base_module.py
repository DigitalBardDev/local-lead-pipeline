from abc import ABC, abstractmethod
from typing import Optional
from core.models import Lead

class BaseModule(ABC):
    name: str = "BaseModule"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def process(self, lead: Lead) -> Lead:
        """
        Processes a single Lead object and returns the updated Lead.
        If the lead should be disqualified from further processing,
        the module can set:
            lead.is_disqualified = True
            lead.disqualification_reason = "..."
        """
        pass
