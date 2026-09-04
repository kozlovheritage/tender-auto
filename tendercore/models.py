from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    PARTICIPATE = "participate"
    CLARIFY = "clarify"
    NOT_PARTICIPATE = "not_participate"
    ERROR = "error"
    NETWORK_ERROR = "network_error"  # HTTP 503 ЕИС — не пишем в БД, повторится


@dataclass
class TenderResult:
    """Замена 9-элементному кортежу из process_tender."""
    reg_number: str
    deadline: str = ""
    doc_path: Optional[str] = None
    decision: Decision = Decision.ERROR
    china_flag: bool = False
    missing_fields: list[str] = field(default_factory=list)
    subject: str = "—"
    nmck: str = "—"
    suppliers_found: bool = False

    @property
    def label(self) -> str:
        return {
            Decision.PARTICIPATE: "Участвуем",
            Decision.CLARIFY: "Требуется уточнение",
            Decision.NOT_PARTICIPATE: "Отказ",
            Decision.ERROR: "Ошибка",
            Decision.NETWORK_ERROR: "Ошибка сети",
        }[self.decision]