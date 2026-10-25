"""Readable, searchable multipage PDF; retains all source blocks in order."""
from __future__ import annotations
from html import escape
import os
from pathlib import Path
import re
import tempfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, LongTable, PageBreak, CondPageBreak, Image,
)

INK = colors.HexColor("#26333B")
MUTED = colors.HexColor("#64737D")
TEAL = colors.HexColor("#007F81")
PALE = colors.HexColor("#F1F6F6")
LINE = colors.HexColor("#DDE5E7")
HEADING = re.compile(r"^\s*---+\s*(.+?)\s*---+\s*$")


def register_fonts():
    if "TenderBody" in pdfmetrics.getRegisteredFontNames():
        return
    here = Path(__file__).resolve().parent / "fonts"
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    options = [
        (here / "DejaVuSans.ttf", here / "DejaVuSans-Bold.ttf"),
        (windows / "arial.ttf", windows / "arialbd.ttf"),
        (windows / "segoeui.ttf", windows / "segoeuib.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in options:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("TenderBody", str(regular)))
            pdfmetrics.registerFont(TTFont("TenderBold", str(bold)))
            pdfmetrics.registerFontFamily("TenderBody", normal="TenderBody", bold="TenderBold",
                                         italic="TenderBody", boldItalic="TenderBold")
            return
    raise RuntimeError("Не найден шрифт с кириллицей для PDF. Нужны DejaVu Sans, Arial или Segoe UI.")


def styles():
    base = dict(fontName="TenderBody", textColor=INK, alignment=TA_LEFT,
                splitLongWords=True, allowWidows=0, allowOrphans=0)
    return {
        "body": ParagraphStyle("TenderBodyStyle", fontSize=10, leading=14,
                               spaceAfter=5, **base),
        "cell": ParagraphStyle("TenderCell", fontSize=9, leading=13, **base),
        "small": ParagraphStyle("TenderSmall", fontSize=8.5, leading=12, spaceAfter=5, **base),
        "title": ParagraphStyle("TenderTitle", fontSize=24, leading=31, spaceAfter=10, **base),
        "h": ParagraphStyle("TenderHeading", fontSize=13, leading=18, spaceBefore=10,
                            spaceAfter=6, keepWithNext=True, **base),
        "badge": ParagraphStyle("TenderDecision", fontSize=13, leading=19, **base),
    }


def markup(text):
    """Escape source XML, support **bold** without interpreting arbitrary tags."""
    text = escape(str(text)).replace("\t", "    ")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text).replace("\n", "<br/>")


def paragraph(text, style):
    return Paragraph(markup(text), style)


def table_cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]


def blocks(response):
    """List, not dict: repeated headings and prose adjacent to tables survive."""
    lines = str(response or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        title = HEADING.match(line)
        if title:
            yield "heading", title.group(1).strip()
            index += 1
        elif line.lstrip().startswith("|") and "|" in line:
            rows = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                row = table_cells(lines[index])
                if not all(re.fullmatch(r"[-:\s]*", cell) for cell in row):
                    rows.append(row)
                index += 1
            if rows:
                yield "table", rows
        else:
            if line.strip():
                yield "paragraph", line.strip()
            index += 1


def source_fields(response):
    result = {}
    for line in str(response).splitlines():
        clean = re.sub(r"\*\*|__", "", line).strip()
        if ":" in clean:
            key, value = clean.split(":", 1)
            result.setdefault(key.strip(), value.strip())
    return result


def excerpt(text, limit=230):
    text = str(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "… (полностью — далее)"


def key_value_rows(rows, style, width, compact=False):
    if compact:
        style = dict(style)
        style["body"] = ParagraphStyle("CompactValue", parent=style["body"], fontSize=9, leading=12, spaceAfter=0)
        style["small"] = ParagraphStyle("CompactKey", parent=style["small"], fontSize=8.5, leading=11, spaceAfter=0)
    data = [[paragraph(key, style["small"]), paragraph(value, style["body"])] for key, value in rows]
    table = LongTable(data, colWidths=[128, width - 128], hAlign="LEFT", splitInRow=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4 if compact else 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if compact else 8),
        ("LINEBELOW", (0, 0), (-1, -1), .4, LINE),
    ]))
    return table


def source_table(rows, style, width):
    count = max(map(len, rows))
    if count > 7:
        # Very wide tables become vertical records; every cell, even unnamed
        # extra columns, is retained rather than shrunk below readable size.
        result = [paragraph("Колонки исходной таблицы: " + " | ".join(rows[0]), style["small"])]
        for row_index, row in enumerate(rows[1:], 1):
            pairs = [(rows[0][i] if i < len(rows[0]) else f"Колонка {i + 1}",
                      row[i] if i < len(row) else "")
                     for i in range(max(len(row), len(rows[0])))]
            result.extend([paragraph(f"Строка таблицы {row_index}", style["small"]),
                           key_value_rows(pairs, style, width)])
        if len(rows) == 1:
            result.append(paragraph(" | ".join(rows[0]), style["body"]))
        return result
    if count == 5:
        weights = [0.06, 0.42, 0.24, 0.12, 0.16]
    else:
        weights = [1 / count] * count
    data = []
    for row_index, row in enumerate(rows):
        padded = row + [""] * (count - len(row))
        data.append([paragraph(value, style["cell"]) for value in padded])
    table = LongTable(data, colWidths=[width * w for w in weights], repeatRows=1,
                      hAlign="LEFT", splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), .4, LINE),
    ]))
    return [table, Spacer(1, 8)]


def build_pdf(reg_number, deadline, response, suppliers_text, path, logistics=None, client_logo=None):
    """Write atomically; keep full source report after the convenience summary."""
    register_fonts()
    style = styles()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width = A4[0] - 96
    fields = source_fields(response)
    decision = next((re.sub(r"\*\*|__", "", line).strip() for line in str(response).splitlines()
                     if re.sub(r"\*\*|__", "", line).strip().lower().startswith("решение:")),
                    "Решение: не указано в аналитике")
    if client_logo is not None:
        client_logo = Path(client_logo)
        if not client_logo.is_file():
            raise FileNotFoundError("Не найден оригинальный логотип Цемторга: " + str(client_logo))
        logo = Image(str(client_logo))
        ratio = logo.imageHeight / logo.imageWidth
        logo.drawWidth, logo.drawHeight = 168, 168 * ratio
        header = Table([[
            [paragraph("ТЕНДЕР АВТО  /  АНАЛИТИКА", style["small"]),
             paragraph("Подготовлено для Цемторга", style["body"])],
            logo,
        ]], colWidths=[width - 168, 168], hAlign="LEFT")
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story = [header, Spacer(1, 18)]
    else:
        story = [paragraph("ТЕНДЕР АВТО  /  АНАЛИТИКА", style["small"])]
    story.extend([
        paragraph("Отчёт по закупке", style["title"]),
        paragraph("№ " + str(reg_number), style["h"]),
    ])
    badge = Table([[paragraph(decision, style["badge"])]], colWidths=[width])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .6, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.extend([badge, Spacer(1, 16)])
    summary = [("Подача заявок до", deadline)]
    for key in ("Предмет закупки", "Заказчик", "НМЦК/НМЦД", "Адрес поставки", "Срок поставки"):
        if key in fields:
            summary.append((key, excerpt(fields[key])))
    if logistics:
        estimate_value = next((value for key, value in logistics["rows"] if key == "Ориентир за один рейс"),
                              "Не рассчитано; причина указана в разделе логистики.")
        summary.append(("Логистика: один рейс", estimate_value))
    story.extend([key_value_rows(summary, style, width), Spacer(1, 16),
                  paragraph("Краткая карточка для просмотра. Полная аналитика, все позиции и условия "
                            "сохранены далее. Решение относится к аналитике, а не к гарантии выигрыша.", style["small"]),
                  PageBreak(), paragraph("Полная аналитика", style["h"])])
    for kind, value in blocks(response):
        if kind == "heading":
            story.append(paragraph(value, style["h"]))
        elif kind == "table":
            story.extend(source_table(value, style, width))
        else:
            story.append(paragraph(value, style["body"]))
    if suppliers_text and suppliers_text.strip():
        story.append(paragraph("Возможные поставщики и контакты", style["h"]))
        for line in suppliers_text.splitlines():
            if line.strip():
                story.append(paragraph(line, style["body"]))
    if logistics:
        story.extend([CondPageBreak(250), Spacer(1, 16), paragraph(logistics["title"], style["title"]),
                      paragraph(logistics["status"], style["h"]),
                      paragraph(logistics["warning"], style["body"]),
                      key_value_rows(logistics["rows"], style, width, compact=True)])

    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(48, A4[1] - 35, A4[0] - 48, A4[1] - 35)
        canvas.setFont("TenderBody", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(48, 27, f"ТЕНДЕР АВТО · № {reg_number}")
        canvas.drawRightString(A4[0] - 48, 27, f"Страница {doc.page}")
        canvas.restoreState()

    fd, temporary = tempfile.mkstemp(prefix=".ta_pdf_", suffix=".pdf", dir=path.parent)
    os.close(fd)
    try:
        doc = SimpleDocTemplate(temporary, pagesize=A4, rightMargin=48, leftMargin=48,
                                topMargin=50, bottomMargin=48,
                                title=f"Закупка № {reg_number}", author="Тендер Авто")
        doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
