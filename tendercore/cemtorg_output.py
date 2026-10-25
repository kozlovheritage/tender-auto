"""Profile-scoped output cleanup; contractual supplier obligations are retained."""
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


def clean_report(text, cemtorg):
    if not cemtorg:
        return text
    lines = []
    skipping = False
    for line in text.splitlines():
        title = line.strip().strip("-=#* ").strip()
        # These are report headings, not every occurrence of 'supplier'.
        excluded = re.fullmatch(
            r"(?:возможные\s+поставщики(?:\s+и\s+контакты)?|"
            r"поставщики(?:\s+и\s+контакты)?|контакты(?:\s+для\s+запроса)?|"
            r"e-?mail(?:s)?|rfq)(?:\s*:.*)?", title, re.I)
        china = re.fullmatch(
            r"доступность\s+закупки\s+в\s+китае(?:\s*:.*)?", title, re.I)
        if excluded:
            skipping = True
            continue
        if china:
            skipping = True
            continue
        heading = re.match(r"^\s*(?:---+|===+|#{1,6}\s)", line)
        field = re.match(
            r"^(?:Решение|Основная информация|Что нужно поставить|"
            r"Критичные требования ТЗ|Нестандартные требования|Заказчик|"
            r"Предмет закупки|Количество позиций|НМЦК/НМЦД|НДС|"
            r"Адрес поставки|Срок поставки|Срок приемки|Срок оплаты|"
            r"Производитель / бренд / страна)(?:\s*:.*)?$", title, re.I)
        if heading or field:
            skipping = False
        if not skipping:
            lines.append(line)
    return "\n".join(lines).strip()


def current_archive(final_dir, date_groups, summary_path=None):
    """Archive this run's reports only; do not delete historical directories."""
    base = Path(final_dir)
    target = Path(str(base) + ".zip")
    fd, temporary = tempfile.mkstemp(prefix=".ta_zip_", suffix=".tmp", dir=base.parent)
    os.close(fd)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            added = set()
            for deadline, paths in date_groups.items():
                for original in paths:
                    relative = Path(str(deadline).replace(".", "_")) / Path(original).name
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("Небезопасный путь отчёта")
                    for item in (relative, relative.with_suffix(".pdf")):
                        if item.as_posix() not in added and (base / item).is_file():
                            archive.write(base / item, item.as_posix())
                            added.add(item.as_posix())
            if summary_path:
                summary = Path(summary_path)
                if summary.parent.resolve() != base.resolve() or not summary.is_file():
                    raise ValueError("Сводка отсутствует или расположена вне итоговой папки")
                archive.write(summary, summary.name)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(target)
