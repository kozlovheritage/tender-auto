"""Сборка промпта для LLM (зеркало монолита)."""
from __future__ import annotations

from tendercore.analysis.master_prompt import MASTER_PROMPT

MAX_DOC_CHARS = 200_000


def build_prompt(doc_text: str, combined_hints: str = "",
                 max_chars: int = MAX_DOC_CHARS) -> str:
    """Полный промпт: мастер + документы + подсказки (как в монолите)."""
    return (MASTER_PROMPT +
            f"\nСодержание документов:\n{doc_text[:max_chars]}\n{combined_hints}")
