#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тендер Авто — GUI v1.3 (PySide6): дизайн-проход этапа 2.
Шапка, карточки, иконки, акценты; темы light/dark/auto (qdarktheme, MIT).
Логика прежняя: QProcess-конвейер, бейджи, история, апдейтер.
"""
import sys, re, json, sqlite3
from pathlib import Path
from html import escape

import qdarktheme
import license_client as lic

from PySide6.QtCore import QTimer, QProcessEnvironment, QProcess, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget)

import sys as _sysf
# >>> CEMTORG-PATCH >>>
import os
def _active_profile():
    _p = os.environ.get('PROFILE', '')
    if not _p:
        try:
            _p = (Path(__file__).resolve().parent / 'config' / 'active_profile.txt').read_text(encoding='utf-8').strip()
        except Exception:
            _p = 'vitro'
    return _p.lower()
def _active_profile_gui():
    _p = os.environ.get('PROFILE', '')
    if not _p:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'active_profile.txt'), encoding='utf-8') as _f:
                _p = _f.read().strip()
        except Exception:
            _p = 'vitro'
    return _p.lower()
CEMTORG_ACTIVE = _active_profile_gui() == 'cemtorg'
print(f'[gui] активный профиль: cemtorg' if CEMTORG_ACTIVE else '[gui] активный профиль: vitro')
HIDE_TABS = ('rfq', 'suppliers', 'рассылка', 'поставщики', 'рфк')
# <<< CEMTORG-PATCH <<<
if getattr(_sysf, "frozen", False):
    BASE = Path(_sysf.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
VERSION = "1.3.0"
REPO = "kozlovheritage/tender-auto"

TQDM_RE = re.compile(r'Тендеры:\s*(\d{1,3})\s*%')
CNT_RE = re.compile(r'\[(\d+)/(\d+)\]')
RFQ_RE = re.compile(r'ОЧЕРЕДЬ RFQ:\s*(\d+)')
THEME_PATH = BASE / "ui_theme.txt"

C_DIM = "#8a90a0"
C_GREEN, C_RED, C_AMBER = "#57ab5a", "#e5534b", "#e3b341"

CUSTOM_QSS = """
QLabel#title   { font-size: 17px; font-weight: 800; letter-spacing: 2px; }
QLabel#dim     { font-size: 12px; }
QPushButton    { min-height: 30px; border-radius: 6px; font-weight: 600; padding: 4px 14px; }
QPushButton#primary { min-height: 34px; font-size: 13px; background: #2e7d5b; color: #fff; border: none; }
QPushButton#primary:hover { background: #35906a; }
QPushButton#primary:disabled { background: #555b6a; color: #c8ccd4; }
QPushButton#danger { color: #e5534b; }
QLabel#badge   { border-radius: 5px; padding: 5px 12px; font-weight: 700; font-size: 12px; }
QTextEdit#log  { font-family: Consolas, 'Courier New', monospace; font-size: 12px; border-radius: 6px; }
QProgressBar   { min-height: 16px; border-radius: 5px; }
QTabBar::tab   { padding: 8px 20px; font-weight: 600; }
QTableWidget   { border-radius: 6px; }
"""

DEC_STYLE = {
    "Участвуем": (C_GREEN, "#10281a"),
    "Требуется уточнение": (C_AMBER, "#2a2210"),
    "Отказ": (C_DIM, "#20242f"),
    "Ошибка": (C_RED, "#2a1a1a"),
}

DEC_MAP = {
    "participate": "Участвуем",
    "участвуем": "Участвуем",
    "clarify": "Требуется уточнение",
    "требуется уточнение": "Требуется уточнение",
    "not_participate": "Отказ",
    "не участвуем": "Отказ",
    "отказ": "Отказ",
    "error": "Ошибка",
    "ошибка": "Ошибка",
}


def _load_theme():
    try:
        return THEME_PATH.read_text(encoding="utf-8").strip() or "dark"
    except Exception:
        return "dark"


def _save_theme(t):
    try:
        THEME_PATH.write_text(t, encoding="utf-8")
    except Exception:
        pass


def _apply_theme(t):
    tt = t if t in ("light", "dark") else "dark"
    try:
        qdarktheme.setup_theme(tt, additional_qss=CUSTOM_QSS)
    except (AttributeError, TypeError):
        try:
            qdarktheme.setup_theme(tt)
            QApplication.instance().setStyleSheet(CUSTOM_QSS)
        except Exception:
            QApplication.instance().setStyleSheet(
                qdarktheme.load_stylesheet(tt) + CUSTOM_QSS)


class UpdateChecker(QThread):
    done = Signal(object)

    def run(self):
        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers={"User-Agent": "TenderAuto"})
            with urllib.request.urlopen(req, timeout=5) as r:
                tag = (json.load(r).get("tag_name") or "").lstrip("v")
            self.done.emit(tag if tag and tag != VERSION else None)
        except Exception:
            self.done.emit(None)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.proc = None
        self.buf_out = self.buf_err = ""
        self.rfq_seen = 0
        self.base_summary = {}
        self.setWindowTitle(f"Тендер Авто — v{VERSION}")
        self.resize(1200, 820)

        root = QWidget(); vbox = QVBoxLayout(root)
        vbox.setContentsMargins(18, 16, 18, 14); vbox.setSpacing(12)

        head = QHBoxLayout(); head.setSpacing(10)
        t = QLabel("ТЕНДЕР АВТО"); t.setObjectName("title")
        ver = QLabel(f"v{VERSION}"); ver.setObjectName("dim")
        self.update_label = QLabel("обновления: проверяю…")
        self.update_label.setObjectName("dim")
        head.addWidget(t); head.addWidget(ver)
        head.addStretch(); head.addWidget(self.update_label)
        vbox.addLayout(head)

        tabs = QTabWidget()
        tabs.addTab(self._tab_run(), "⚙ Анализ")
        tabs.addTab(self._tab_history(), "🗂 История")
        tabs.addTab(self._tab_settings(), "🎛 Настройки")
        vbox.addWidget(tabs, 1)
        self.setCentralWidget(root)

        self.checker = UpdateChecker()
        self.checker.done.connect(self._on_update)
        self.checker.start()
        # ── лицензия (этап 3) ──
        self._license_gate()
        QTimer.singleShot(300, self._selftest)

    # ── вкладки ─────────────────────────────────────────
    def _tab_run(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(4, 12, 4, 4); v.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(8)
        self.btn_sample = QPushButton("⚙ Собрать выборку")
        self.btn_run = QPushButton("▶ Запустить анализ")
        self.btn_rfq = QPushButton("✉ Отправить RFQ")
        # >>> CEMTORG-HIDE >>>
        if CEMTORG_ACTIVE:
            for _attr in ('btn_rfq', 'b_rfq', 'badge_rfq', 'lbl_rfq'):
                _w = getattr(self, _attr, None)
                if _w is not None:
                    try:
                        _w.hide()
                    except Exception:
                        pass
        # <<< CEMTORG-HIDE <<<

        if CEMTORG_ACTIVE:
            self.btn_rfq.setVisible(False)  # CEMTORG_HIDE_BTN_RFQ
        self.btn_run.setObjectName("primary")
        self.btn_open = QPushButton("📁 Отчёты")
        self.btn_stop = QPushButton("■ Стоп")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setEnabled(False)
        for b in (self.btn_sample, self.btn_run, self.btn_rfq,
                  self.btn_open, self.btn_stop):
            top.addWidget(b)
        v.addLayout(top)

        badges = QHBoxLayout(); badges.setSpacing(8)
        self.b_part = self._badge("Участвуем: 0")
        self.b_clar = self._badge("Уточнение: 0")
        self.b_rej = self._badge("Отказ: 0")
        self.b_err = self._badge("Ошибка: 0")
        self.b_rfq = self._badge("RFQ: 0")
        if CEMTORG_ACTIVE:
            self.b_rfq.setVisible(False)  # CEMTORG_HIDE_BADGE_RFQ
        for b in (self.b_part, self.b_clar, self.b_rej, self.b_err, self.b_rfq):
            badges.addWidget(b)
        badges.addStretch()
        v.addLayout(badges)

        self.status_lbl = QLabel("Готов.")
        self.status_lbl.setObjectName("dim")
        if CEMTORG_ACTIVE:
            self.status_lbl.setWordWrap(True)
            self.status_lbl.setMinimumHeight(24)
            self.status_lbl.setMaximumHeight(48)
        v.addWidget(self.status_lbl)

        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setObjectName("log")
        if CEMTORG_ACTIVE:
            self.log.hide()
            v.addWidget(self.log, 2)

        self.progress = QProgressBar(); self.progress.setRange(0, 100)
        v.addWidget(self.progress)
        if CEMTORG_ACTIVE:
            v.addStretch(1)
        else:
            v.addWidget(self.log, 1)

        self.btn_sample.clicked.connect(lambda: self._start(["sampler.py"]))
        self.btn_run.clicked.connect(lambda: self._start(["tender_auto.py"]))
        self.btn_rfq.clicked.connect(self._on_rfq)
        self.btn_open.clicked.connect(self._open_output)
        self.btn_stop.clicked.connect(self._stop)
        return w

    def _badge(self, text):
        lb = QLabel(text); lb.setObjectName("badge")
        if CEMTORG_ACTIVE:
            lb.setFixedHeight(34)  # CEMTORG_SAMPLER_UI_PATCH
        lb.setStyleSheet(f"background:#20242f; color:{C_DIM};")
        return lb

    def _tab_history(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(4, 12, 4, 4); v.setSpacing(10)
        self.history_table = QTableWidget()
        self.history_table.setAlternatingRowColors(True)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.history_table, 1)
        b = QPushButton("⟳ Обновить")
        b.clicked.connect(self._refresh_history)
        v.addWidget(b)
        self._refresh_history()
        return w

    def _tab_settings(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(4, 12, 4, 4); v.setSpacing(10)
        v.addWidget(QLabel("Тема оформления:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Тёмная", "Светлая", "Как в системе"])
        self.theme_combo.setCurrentIndex(
            {"dark": 0, "light": 1, "auto": 2}.get(_load_theme(), 0))
        self.theme_combo.currentIndexChanged.connect(self._on_theme)
        v.addWidget(self.theme_combo)
        v.addWidget(QLabel(f"Папка проекта: {BASE}"))
        v.addWidget(QLabel(f"Отчёты: {BASE / 'output'}"))
        v.addWidget(QLabel("Ключи API: secrets.txt (GUI их не хранит)."))
        v.addWidget(QLabel("Пороги: config/settings.toml · Выборка: sampler_config.txt"))
        v.addStretch()
        return w

    def _on_theme(self, i):
        t = {0: "dark", 1: "light", 2: "auto"}[i]
        _save_theme(t)
        _apply_theme(t)

    def _open_output(self):
        out = BASE / "output"
        try:
            out.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    # ── бейджи и сводка ─────────────────────────────────
    def _summary(self):
        counts = {}
        db = BASE / "data" / "decisions.db"
        if not db.exists():
            return counts
        try:
            con = sqlite3.connect(str(db)); cur = con.cursor()
            if "decisions" in [t[0] for t in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]:
                cols = [c[1] for c in cur.execute("PRAGMA table_info(decisions)")]
                dec = next((c for c in cols
                            if "decision" in c.lower() or "решен" in c.lower()), None)
                if dec:
                    for val, n in cur.execute(
                            f'SELECT "{dec}", COUNT(*) FROM decisions GROUP BY "{dec}"'):
                        key = DEC_MAP.get(str(val).strip().lower(), str(val))
                        counts[key] = counts.get(key, 0) + int(n)
            con.close()
        except Exception:
            pass
        return counts

    def _set_badge(self, lb, text, key):
        fg, bg = DEC_STYLE.get(key, (C_DIM, "#20242f"))
        lb.setText(text)
        lb.setStyleSheet(f"background:{bg}; color:{fg};")

    def _update_badges(self, d):
        self._set_badge(self.b_part, f"Участвуем: {d.get('Участвуем', 0)}", "Участвуем")
        self._set_badge(self.b_clar, f"Уточнение: {d.get('Требуется уточнение', 0)}",
                        "Требуется уточнение")
        self._set_badge(self.b_rej, f"Отказ: {d.get('Отказ', 0)}", "Отказ")
        self._set_badge(self.b_err, f"Ошибка: {d.get('Ошибка', 0)}", "Ошибка")
        self._set_badge(self.b_rfq, f"RFQ: {self.rfq_seen}", "Требуется уточнение")

    # ── процессы ───────────────────────────────────────
    def _start(self, args):
        if self.proc is not None and \
                self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Занято", "Процесс уже выполняется.")
            return
        self.base_summary = self._summary()
        self.rfq_seen = 0
        self._active_job = Path(args[0]).stem
        self._sampler_result = ""
        self._sampler_error = ""
        if CEMTORG_ACTIVE:
            # Keep the selection transcript above the analysis journal.
            # A new selection starts a new transcript; analysis never erases it.
            if self._active_job == "sampler":
                self.log.clear()
            self.log.show()
            self.log.document().setMaximumBlockCount(0)
            if self._active_job == "tender_auto":
                self._analysis_tender = ""
                self._analysis_failure = ""
                self._analysis_failure_shown = False
                self._analysis_traceback = False
                self._analysis_paused = False
                self._analysis_issues = False
                self._analysis_cancelled = False
                self._analysis_skipped = 0
                self._analysis_retries = 0
                if not hasattr(self, "_analysis_timer"):
                    self._analysis_timer = QTimer(self)
                    self._analysis_timer.setInterval(1000)
                    self._analysis_timer.timeout.connect(self._analysis_tick)
                self._analysis_stage("Подготовка аналитики")
                self._analysis_timer.start()
        # Live-счётчик ТЕКУЩЕГО прогона; финальные значения возьмём из БД в _finished
        self.live_counts = {"Участвуем": 0, "Требуется уточнение": 0,
                            "Отказ": 0, "Ошибка": 0}
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(BASE))
        self.proc.readyReadStandardOutput.connect(self._read_out)
        self._run_buf = b""
        self.proc.finished.connect(self._on_proc_finished)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._finished)
        if CEMTORG_ACTIVE:
            self.proc.errorOccurred.connect(self._on_proc_error)
        self.btn_stop.setEnabled(True)
        self.btn_run.setEnabled(False); self.btn_sample.setEnabled(False)
        if CEMTORG_ACTIVE and self._active_job == "sampler":
            self.progress.setRange(0, 0)
            self.status_lbl.setText("Сбор выборки с ЕИС…")
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status_lbl.setText("Выполняется…")
        self._log(f"▶ python {' '.join(args)}", C_DIM)
        prog, pargs = self._proc_cmd(args)
        _env = QProcessEnvironment.systemEnvironment()
        _env.insert("PYTHONUNBUFFERED", "1")
        if CEMTORG_ACTIVE:
            _env.insert("PYTHONIOENCODING", "utf-8")
            _env.insert("TA_GUI_PROGRESS", "1")
        self.proc.setProcessEnvironment(_env)
        self.proc.start(prog, pargs)

    def _proc_cmd(self, args):
        if getattr(sys, "frozen", False):
            stem = Path(args[0]).stem
            sub = {"tender_auto": "engine", "sampler": "sampler"}.get(stem, "")
            exe = Path(sys.executable).resolve().parent / sub / (stem + ".exe")
            return str(exe), list(args[1:])
        return sys.executable, ["-u"] + args

    def _stop(self):
        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "tender_auto":
            self._analysis_cancelled = True
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()
            if not self.proc.waitForFinished(3000):
                self.proc.kill()
            self._log("■ Остановлено пользователем.", C_DIM)

    def _on_proc_error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        proc = self.sender()
        detail = proc.errorString() if proc else "неизвестная ошибка"
        if getattr(self, "_active_job", "") == "sampler":
            self._sampler_error = detail
        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "tender_auto":
            self._analysis_failure = "Не удалось запустить анализатор: " + detail
            self._analysis_done(1, QProcess.ExitStatus.NormalExit)
        self.status_lbl.setText(f"Не удалось запустить процесс: {detail}")
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(True)
        self.btn_sample.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

    def _finished(self, code, status):
        self.btn_stop.setEnabled(False)
        self.btn_run.setEnabled(True); self.btn_sample.setEnabled(True)
        self.proc = None
        new = self._summary()
        diff = {k: max(0, new.get(k, 0) - self.base_summary.get(k, 0)) for k in new}
        
        # Показываем итоги ТЕКУЩЕГО прогона (дельта БД) — авторитетный источник
        self._update_badges(diff)
        
        # Считаем RFQ-очередь
        rfq_count = 0
        rfq_path = BASE / "data" / "rfq_queue.json"
        if rfq_path.exists():
            try:
                import json
                with open(rfq_path, encoding="utf-8") as f:
                    q = json.load(f)
                rfq_count = len(q) if isinstance(q, list) else len(q.get("tenders", []))
            except Exception:
                pass
        self.rfq_seen = rfq_count
        self._set_badge(self.b_rfq, f"RFQ: {rfq_count}", "Требуется уточнение")
        
        total_new = sum(diff.values())
        total_all = sum(new.values())
        self._log(f"■ Завершено с кодом {code}. Новых решений: {total_new}. Всего в БД: {total_all}.",
                  C_GREEN if code == 0 else C_RED)
        self.status_lbl.setText(
            f"Готово. Всего: {total_all} · Участвуем {new.get('Участвуем', 0)} · "
            f"Уточнение {new.get('Требуется уточнение', 0)} · "
            f"Отказ {new.get('Отказ', 0)} · Ошибок {new.get('Ошибка', 0)} · "
            f"RFQ: {rfq_count}")
        if code == 77:
            self.status_lbl.setText("ЕИС: прогон приостановлен. Готовые результаты сохранены; повторите запуск позже.")
        elif code == 75:
            self.status_lbl.setText("ЕИС: уже идёт другой запуск. Дождитесь его завершения.")

        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "sampler":
            self.progress.setRange(0, 100)
            self.progress.setValue(100 if code == 0 else 0)
            if self._sampler_error and self._sampler_result:
                self.status_lbl.setText(
                    "Сбор прерван: " + self._sampler_error[:120]
                    + " | " + self._sampler_result[:120]
                )
            elif self._sampler_error:
                self.status_lbl.setText(
                    "Сбор выборки остановлен: " + self._sampler_error[:180]
                )
            elif code == 0 and self._sampler_result:
                self.status_lbl.setText(self._sampler_result)
            elif code == 77:
                self.status_lbl.setText(
                    "ЕИС приостановила сбор; подробность показана выше."
                )
            elif code == 75:
                self.status_lbl.setText(
                    "Сбор уже запущен в другом окне программы."
                )
            elif code != 0:
                self.status_lbl.setText(
                    f"Сбор выборки завершился с ошибкой (код {code}); "
                    "смотрите сообщения выше."
                )
            else:
                self.status_lbl.setText(
                    "Сбор завершён; итог показан в сообщениях выше."
                )
        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "tender_auto":
            self._analysis_done(code, status)
        self._refresh_history()

    def _read_out(self):
        data = bytes(self.proc.readAllStandardOutput())
        self._run_buf += data
        self._feed(data, "out")

    def _read_err(self):
        data = bytes(self.proc.readAllStandardError())
        self._run_buf += data
        self._feed(data, "err")

    def _feed(self, data, stream):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1251", "replace")
        m = RFQ_RE.search(text)
        if m:
            self.rfq_seen = int(m.group(1))
            self._set_badge(self.b_rfq, f"RFQ: {self.rfq_seen}", "Требуется уточнение")
        m = TQDM_RE.search(text)
        if m:
            self.progress.setValue(int(m.group(1)))
        m = CNT_RE.search(text)
        if m and not (CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "tender_auto"):
            self.status_lbl.setText(f"Тендер {m.group(1)} из {m.group(2)}")
        buf = (self.buf_out if stream == "out" else self.buf_err) + text
        parts = re.split(r'[\n\r]+', buf)
        tail = parts.pop()
        if stream == "out":
            self.buf_out = tail
        else:
            self.buf_err = tail
        for ln in parts:
            self._handle(ln)


    # TA_FRIENDLY_PROGRESS
    def _analysis_stage(self, text, kind="info"):
        import time
        from datetime import datetime
        if kind == "tender":
            self._analysis_tender = text
            text = "Проверка условий закупки"
        self._analysis_stage_text = text
        self._analysis_stage_at = time.monotonic()
        color = {"error": C_RED, "pause": C_AMBER, "warning": C_AMBER,
                 "result": C_GREEN}.get(kind, C_DIM)
        title = getattr(self, "_analysis_tender", "")
        shown = (title + " — " if kind == "tender" and title else "") + text
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(
            f'<span style="color:{color}">{escape(stamp + " · " + shown)}</span>')
        self._analysis_tick()

    def _analysis_tick(self):
        import time
        text = getattr(self, "_analysis_stage_text", "Подготовка")
        elapsed = max(0, int(time.monotonic() - getattr(
            self, "_analysis_stage_at", time.monotonic())))
        title = getattr(self, "_analysis_tender", "")
        self.status_lbl.setText(
            (title + " · " if title else "") + text + f" · этап: {elapsed} с")

    def _analysis_line(self, line):
        line = line.strip()
        if line.startswith("@@TA_PROGRESS@@"):
            try:
                event = json.loads(line[len("@@TA_PROGRESS@@"):])
                kind = event.get("kind", "info")
                if kind == "pause":
                    self._analysis_paused = True
                if kind in ("error", "warning"):
                    self._analysis_issues = True
                if kind == "result":
                    decision = event.get("decision")
                    # TA_SEPARATE_EIS_RETRIES
                    key = {"participate": "Участвуем",
                           "clarify": "Требуется уточнение",
                           "not_participate": "Отказ",
                           "error": "Ошибка", "Ошибка": "Ошибка"}.get(decision)
                    if key:
                        self.live_counts[key] = self.live_counts.get(key, 0) + 1
                        self._update_badges(self.live_counts)
                    if decision == "network_error":
                        self._analysis_retries += 1
                    if decision in ("error", "Ошибка", "network_error"):
                        kind = "warning"
                self._analysis_stage(str(event["text"]), kind)
            except (ValueError, KeyError, TypeError):
                self._analysis_issues = True
                self._analysis_stage("Не удалось прочитать сообщение этапа.", "warning")
            return True
        if line.startswith("Решение:"):
            return True  # Counters use the single authoritative result event.
        if "Ошибка чтения Excel:" in line:
            self._analysis_failure = (
                "Не удалось прочитать выгрузку Excel. Закрой Excel и проверь файл.")
        elif "[ОШИБКА] Excel-файл не найден" in line:
            self._analysis_failure = "В папке программы не найдена выгрузка Excel."
        elif "Traceback" in line or re.search(
                r"\b[\w.]+(?:Error|Exception|Timeout):", line):
            self._analysis_issues = True
            if not getattr(self, "_analysis_traceback", False):
                self._analysis_stage(
                    "Ошибка выполнения. Технические подробности будут сохранены в logs.",
                    "error")
            self._analysis_traceback = True
        elif "ЕИС:" in line and not any(
                word in line.lower() for word in ("поставщик", "email", "rfq")):
            self._analysis_issues = True
            if any(word in line.lower() for word in (
                    "приостанов", "прогресс сохранён", "новых запросов нет")):
                self._analysis_paused = True
            self._analysis_stage(line[:320], "warning")
        elif "уже обработан" in line:
            number = re.search(r"Тендер\s+(\d+)", line)
            self._analysis_skipped += 1
            self._analysis_stage(
                ("№" + number.group(1) + ": " if number else "")
                + "уже обработан — пропущен.")
        if (getattr(self, "_analysis_failure", "")
                and not getattr(self, "_analysis_failure_shown", False)):
            self._analysis_stage(self._analysis_failure, "error")
            self._analysis_failure_shown = True
            return True
        return False

    def _analysis_done(self, code, status):
        timer = getattr(self, "_analysis_timer", None)
        if timer:
            timer.stop()
        self.progress.setRange(0, 100)
        if getattr(self, "_analysis_cancelled", False):
            message = "Анализ остановлен пользователем; сохранённые результаты оставлены."
            kind = "warning"
        elif getattr(self, "_analysis_paused", False) or code in (75, 77):
            message = "Анализ приостановлен ЕИС. Причина и время ожидания — в журнале выше."
            kind = "pause"
        elif (code != 0 or status == QProcess.ExitStatus.CrashExit
              or getattr(self, "_analysis_failure", "")):
            message = getattr(self, "_analysis_failure", "") or (
                f"Анализ завершился с ошибкой (код {code}). Подробности — в logs.")
            kind = "error"
        else:
            count = sum(self.live_counts.values())
            message = (f"Прогон завершён. Решений: {count}; "
                       f"ЕИС на повтор: {self._analysis_retries}; "
                       f"пропущено: {self._analysis_skipped}.")
            if getattr(self, "_analysis_issues", False):
                message += " Есть предупреждения — смотри журнал."
            kind = "warning" if self._analysis_issues else "result"
        if kind == "error":
            self.progress.setValue(0)
        self._analysis_tender = ""
        self._analysis_stage(message, kind)
        self.status_lbl.setText(message)
        self._update_badges(self.live_counts)
        if (kind == "error" or getattr(self, "_analysis_traceback", False)) and code in (0, -1):
            from datetime import datetime
            folder = BASE / "logs"
            folder.mkdir(exist_ok=True)
            name = "error_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
            (folder / name).write_bytes(bytes(getattr(self, "_run_buf", b"")))

    def _handle(self, s):
        if (CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "sampler"
                and s.strip().startswith("@@TA_PROGRESS@@")):
            try:
                event = json.loads(s.strip()[len("@@TA_PROGRESS@@"):])
                text = str(event["text"])
                self._log(text, C_AMBER)
                self.status_lbl.setText(text)
            except (ValueError, KeyError, TypeError):
                self._log("Не удалось прочитать сообщение ЕИС.", C_AMBER)
            return
        if (CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "tender_auto"
                and self._analysis_line(s)):
            return
        s = s.rstrip()
        if not s.strip() or TQDM_RE.search(s):
            return
        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") == "sampler":
            if (s.startswith("📅 Окно дат:") or s.startswith("📄 Страница")
                    or "новых строк:" in s or s.startswith("🔎 запрос")):
                self.status_lbl.setText(s.strip())
            if "ВЫБОРКА:" in s:
                self._sampler_result = s.strip()
            elif "Ничего не найдено" in s:
                self._sampler_result = "Выборка завершена: тендеры не найдены."
            elif s.startswith("ЕИС: выборка неполная"):
                self._sampler_error = s.strip()
                self.status_lbl.setText(s.strip())
            elif "Traceback" in s or re.search(r"\b[\w.]+(?:Error|Exception|Timeout):", s):
                self._sampler_error = s.strip()
                self.status_lbl.setText("Ошибка сборщика: " + s.strip()[:140])
        u = s.upper()
        if s.lstrip().startswith("Решение:"):
            if "ТРЕБУЕТСЯ УТОЧНЕНИЕ" in u:
                color, _key = C_AMBER, "Требуется уточнение"
            elif "НЕ УЧАСТВУЕМ" in u:
                color, _key = C_DIM, "Отказ"
            elif "ОШИБКА" in u:
                color, _key = C_RED, "Ошибка"
            else:
                color, _key = C_GREEN, "Участвуем"
            self.live_counts[_key] = self.live_counts.get(_key, 0) + 1
            self._update_badges(self.live_counts)
        elif "❌" in s or "⛔" in s or "ОШИБКА" in u:
            color = C_RED
        elif "✅" in s:
            color = C_GREEN
        elif "⚠" in s:
            color = C_AMBER
        else:
            color = None
        self._log(s, color)

    def _log(self, text, color=None):
        if CEMTORG_ACTIVE and getattr(self, "_active_job", "") != "sampler":
            return
        sb = self.log.verticalScrollBar()
        # Проверяем, находится ли скролл внизу (с допуском 20 пикселей)
        at_bottom = sb.value() >= sb.maximum() - 20
        
        if color:
            self.log.append(f'<span style="color:{color}">{escape(text)}</span>')
        else:
            self.log.append(escape(text))
        
        # Автоскролл только если пользователь сам не прокрутил вверх
        if at_bottom:
            sb.setValue(sb.maximum())

    # ── история ─────────────────────────────────────────
    def _refresh_history(self):
        rows = self._load_history()
        if not rows:
            self.history_table.setColumnCount(1)
            self.history_table.setHorizontalHeaderLabels(["История пуста"])
            self.history_table.setRowCount(0)
            return
        head, data = rows
        self.history_table.setColumnCount(len(head))
        self.history_table.setHorizontalHeaderLabels([str(h) for h in head])
        self.history_table.setRowCount(len(data))
        dec_idx = next((j for j, h in enumerate(head)
                        if "решен" in str(h).lower() or "decision" in str(h).lower()),
                       None)
        for i, r in enumerate(data):
            for j, val in enumerate(r):
                it = QTableWidgetItem("" if val is None else str(val))
                if j == dec_idx:
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(DEC_STYLE.get(str(val), (C_DIM,))[0]))
                self.history_table.setItem(i, j, it)

    def _load_history(self):
        db = BASE / "data" / "decisions.db"
        try:
            if db.exists():
                con = sqlite3.connect(str(db)); cur = con.cursor()
                tabs = [t[0] for t in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                for t in tabs:
                    cols = [c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')]
                    data = cur.execute(
                        f'SELECT * FROM "{t}" ORDER BY rowid DESC LIMIT 500').fetchall()
                    if data:
                        con.close()
                        return cols, data
                con.close()
        except Exception:
            pass
        hx = BASE / "data" / "history.xlsx"
        try:
            if hx.exists():
                from openpyxl import load_workbook
                wb = load_workbook(str(hx), read_only=True, data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(max_row=501, values_only=True))
                wb.close()
                if rows:
                    return rows[0], [r for r in rows[1:]
                                     if any(c is not None for c in r)]
        except Exception:
            pass
        return None


    # ── лицензия ────────────────────────────────────────
    def _lic_enabled(self):
        try:
            import tomllib
            p = BASE / "config" / "settings.toml"
            if p.exists():
                with open(p, "rb") as f:
                    return bool(tomllib.load(f).get("license", {}).get("enabled", False))
        except Exception:
            pass
        return False


    def _buf_out(self):
        self._run_buf += self.proc.readAllStandardOutput()

    def _on_proc_finished(self, code, status):
        if self.proc is not None:
            self._read_out()
            self._read_err()
        for attr in ("buf_out", "buf_err"):
            tail = getattr(self, attr, "")
            setattr(self, attr, "")
            if tail:
                self._handle(tail)
        if code not in (0, -1):
            import os, datetime
            d = os.path.join(str(BASE), 'logs')
            os.makedirs(d, exist_ok=True)
            fn = os.path.join(d, 'error_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.log')
            with open(fn, 'wb') as fh:
                fh.write(getattr(self, '_run_buf', b''))
            self.statusBar().showMessage(f'❌ код {code}; лог: {fn}', 20000)

    def _selftest(self):
        import os
        prog, pargs = self._proc_cmd(['tender_auto.py', '--selftest'])
        from PySide6.QtCore import QProcess
        p = QProcess(self)
        p.setWorkingDirectory(str(BASE))
        p.start(prog, pargs)
        if not p.waitForFinished(20000):
            p.kill(); return
        out = bytes(p.readAllStandardOutput()).decode('utf-8', 'replace')
        d = os.path.join(str(BASE), 'logs'); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'selftest.log'), 'w', encoding='utf-8') as fh:
            fh.write(out)
        bad = [ln for ln in out.splitlines() if '❌' in ln and 'резерв' not in ln and 'RFQ' not in ln]
        if bad:
            self.statusBar().showMessage('⚠️ Диагностика: ' + '; '.join(bad)[:120], 15000)

    def _on_rfq(self):
        self._start(["tender_auto.py", "--send-rfq"])

    def _license_gate(self):
        ok, msg, info = lic.validate(enabled=self._lic_enabled())
        if ok:
            self.statusBar().showMessage(f"Лицензия: {msg}")
            return
        from PySide6.QtWidgets import QInputDialog
        key, okb = QInputDialog.getText(
            self, "Активация", f"{msg}.\nВведите лицензионный ключ:")
        if okb and key.strip():
            lic.save_key(key)
            ok, msg, info = lic.validate(enabled=True)
        if ok:
            self.statusBar().showMessage(f"Лицензия: {msg}")
        else:
            self.btn_run.setEnabled(False)
            self.btn_sample.setEnabled(False)
            self.btn_rfq.setEnabled(False)
            self.status_lbl.setText(f"🔒 {msg}")
            self.statusBar().showMessage("Лицензия не активирована — анализ заблокирован.")

    def _on_update(self, tag):
        if tag:
            self.update_label.setText(f"доступна версия v{tag} (GitHub Releases)")
            self.update_label.setStyleSheet(f"color:{C_AMBER};")
        else:
            self.update_label.setText("обновлений нет")
            self.update_label.setStyleSheet(f"color:{C_DIM};")

    def closeEvent(self, ev):
        if self.proc is not None and \
                self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()
            self.proc.waitForFinished(2000)
        ev.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    _apply_theme(_load_theme())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
# TA_CEMTORG_WEEK_V1
