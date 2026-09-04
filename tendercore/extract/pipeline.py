"""tendercore.extract.pipeline — агрегация текста + умные секции + инъекция брендов."""
from __future__ import annotations
import os

from tendercore.log import get_logger
from tendercore.extract.text import (MAX_TEXT_PER_FILE, MAX_TEXT_TOTAL,
                                     extract_text_from_file, is_critical_file)
from tendercore.extract.sections import extract_relevant_sections

log = get_logger("extract")

_ERR_PREFIXES = ("[Ошибка", "[OCR не дал текста]", "[OCR недоступен]",
                 "[PDF parsing not available]", "[Ошибка чтения .doc]")


def extract_texts_from_paths(downloaded_paths, max_total=MAX_TEXT_TOTAL,
                             max_per_file=MAX_TEXT_PER_FILE, brand_scanner=None):
    """Извлекает и объединяет текст; опционально сканирует бренды по полному тексту.

    brand_scanner(text, filename) -> str|None (напр. brand.extract_manufacturer_from_chunks).
    Возвращает (doc_text, critical_errors, success_files, extraction_errors, brand_hints).
    """
    doc_text, extraction_errors, success_files, brand_hints = "", [], [], []
    total = 0
    for fpath in downloaded_paths:
        filename = os.path.basename(fpath)
        text = extract_text_from_file(fpath)
        if text and not text.startswith(_ERR_PREFIXES):
            if brand_scanner:
                fb = brand_scanner(text, filename)
                if fb:
                    brand_hints.append(fb)
                    log.info(f"🔎 Полный скан «{filename}»: производитель → {fb}")
            file_text = extract_relevant_sections(text, first_chars=max_per_file)
            block = f"\n--- Начало файла {filename} ---\n{file_text}\n--- Конец файла ---\n"
            doc_text += block
            total += len(block)
            success_files.append(filename)
            if total >= max_total:
                log.warning(f"⚠️ Лимит текста ({max_total}) — остальные файлы пропущены")
                break
        else:
            extraction_errors.append((filename, (text or "пусто")[:100]))
            log.warning(f"⚠️ Ошибка извлечения из {filename}")
    if brand_hints:
        uniq = list(dict.fromkeys(brand_hints))
        doc_text = ("\n[ПРОИЗВОДИТЕЛИ ИЗ ПОЛНОГО СКАНА: " + ", ".join(uniq) + "]\n"
                    ) + doc_text
        log.info(f"💡 Инжектировано в промпт: {', '.join(uniq)}")
    if doc_text.strip():
        critical = [n for n, _ in extraction_errors if is_critical_file(n, success_files)]
    else:
        critical = [n for n, _ in extraction_errors]
    return doc_text, critical, success_files, extraction_errors, brand_hints