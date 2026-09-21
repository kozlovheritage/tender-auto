# Tender Auto / Тендер Авто

**EN** — Automated screening assistant for Russian public procurement
(44-FZ / 223-FZ). Collects a daily sample from zakupki.gov.ru, downloads
tender documentation, extracts text (DOC/DOCX/XLS/XLSX/PDF/OCR/ZIP/RAR/ODS/PPTX),
runs LLM analysis against 20 business stop-factors, re-validates the answer
with 13 Python post-checks, searches international suppliers with email
discovery and MX validation, and produces a structured Word report.

**RU** — автоматизированный скрининг тендеров госзакупок (44-ФЗ / 223-ФЗ):
ежедневная выборка с zakupki.gov.ru, скачивание документации, извлечение
текста из любых форматов, LLM-анализ по 20 стоп-факторам, пост-валидация
ответа кодом, поиск международных поставщиков с подбором email и
MX-валидацией, Word-отчёт по каждому тендеру.

## Features / Возможности

- **Sampler / сэмплер** — сбор выборки из поиска ЕИС: ценовое окно,
  дедлайны, дедупликация по истории, фильтры-стоп-слова (v15–v17).
- **Fast pre-checks / предпроверки** — стоп-факторы по названию
  до скачивания файлов (без LLM и сети).
- **LLM decision + post-validation** — решение принимает LLM, но срок
  поставки, ГОСТ, нацрежим, казначейка, дженерик-тендеры и др.
  перепроверяются Python-кодом (13 пост-проверок).
- **Robust downloading** — retry с длинными паузами при HTTP 503,
  SSL-фолбэк при ТСПУ/прокси, SPA-типы извещений (ea20/ea15), GUID-кэш.
- **Suppliers / поставщики** — веб-поиск (LangSearch), LLM-очистка выдачи,
  скрапинг контактных страниц, MX-валидация, RFQ-фильтр адресов
  (только sales/export, без hr/legal/noreply).
- **Word reports / отчёты** — структурированный отчёт: решение, спецификация,
  бренд/страна, сроки, поставщики, контакты.
- **History & checkpoint** — `data/history.xlsx`, `data/decisions.db`,
  возобновление прерванного прогона, дедупликация.
- **tendercore** — вынесенное бизнес-ядро (precheck / postcheck / brand /
  extract / eis / report) + загрузчик `config/settings.toml`.
- **Shadow parity** — теневой контур сверки монолита и ядра, офлайн A/B-тесты.

## Requirements / Требования

- Python 3.11+ (Windows рекомендуется: чтение `.doc` через Word COM)
- `pip install -r requirements.txt`
- Опционально: Tesseract OCR (сканы), Microsoft Word (`.doc`)

## Quick start / Быстрый старт

```bash
pip install -r requirements.txt

# ключи — в secrets.txt рядом со скриптом (НЕ в репозиторий):
#   DEEPSEEK_API_KEY=sk-...
#   LANGSEARCH_API_KEY=...

python sampler.py          # выборка из ЕИС → выгрузка_<дата>.xlsx
python tender_auto.py      # скрининг → итоги_прогона_<дата>.xlsx + Word
python -m pytest tests/ -q # тесты