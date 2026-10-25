"""PDF companions, while preserving DOCX/RFQ compatibility during rollout."""
from pathlib import Path
import shutil

from tendercore.cemtorg_output import clean_report
from tendercore.report.pdf_report import build_pdf
from tendercore.logistics import estimate


def save_pdf(reg, deadline, response, suppliers, doc_path, cemtorg=False, config_path=None):
    source = clean_report(response, cemtorg)
    logistics = estimate(source, config_path) if cemtorg else None
    logo = Path(__file__).resolve().parent / "assets/cemtorg_logo.png" if cemtorg else None
    return build_pdf(reg, deadline, source, "" if cemtorg else suppliers,
                     Path(doc_path).with_suffix(".pdf"), logistics=logistics, client_logo=logo)


def ensure_pdf(reg, deadline, doc_path, cemtorg=False, config_path=None):
    """Recover a current-run orphan without an LLM call or deleting history.

    Old DOCX is read in document order; every existing paragraph/table cell is
    kept. This does not claim to restore text already absent in an old DOCX.
    """
    pdf = Path(doc_path).with_suffix(".pdf")
    if pdf.is_file():
        return pdf
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(doc_path)
    lines = []
    for element in doc.element.body:
        if element.tag.endswith("}p"):
            text = Paragraph(element, doc).text
            if text:
                lines.append(text)
        elif element.tag.endswith("}tbl"):
            table = Table(element, doc)
            for row in table.rows:
                lines.append("| " + " | ".join(cell.text.replace("|", "\\|").replace("\n", " / ")
                                                for cell in row.cells) + " |")
    return save_pdf(reg, deadline, "\n".join(lines), "", doc_path, cemtorg, config_path)


def copy_report_pair(doc_path, folder):
    """Don't silently deliver DOCX-only if PDF generation failed."""
    doc_path, folder = Path(doc_path), Path(folder)
    pdf = doc_path.with_suffix(".pdf")
    if not pdf.is_file():
        raise RuntimeError(f"Не найден PDF для отчёта {doc_path.name}; повторите обработку.")
    shutil.copy2(doc_path, folder)
    shutil.copy2(pdf, folder)
