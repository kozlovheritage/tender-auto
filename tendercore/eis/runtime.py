"""EIS pacing, persisted cooldowns and one active run per product folder."""
from __future__ import annotations

import contextlib
import functools
import errno
import json
import math
import os
import random
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit


class EisNetworkError(Exception):
    """Retryable acquisition error, never a business refusal."""


class EisStopError(EisNetworkError):
    """Stop the source, save progress and resume after retry_at."""

    def __init__(self, reason, retry_at=0, status=None):
        self.reason = str(reason)
        self.retry_at = float(retry_at)
        self.status = status
        when = datetime.fromtimestamp(self.retry_at).strftime("%d.%m %H:%M:%S") if self.retry_at else "позже"
        super().__init__(f"{self.reason}. Повторный запуск: {when}")


def application_data_dir():
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        if root.name.lower() in ("engine", "sampler"):
            root = root.parent
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "data"


def retry_after_seconds(value, now):
    if value is None:
        return None
    try:
        number = float(value)
        return max(0.0, number) if math.isfinite(number) else None
    except (ValueError, TypeError):
        try:
            stamp = parsedate_to_datetime(str(value))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return max(0.0, stamp.timestamp() - now)
        except (ValueError, TypeError, OverflowError):
            return None


class FileLock:
    """OS-released lock; no stale PID files or third-party dependencies."""

    def __init__(self, path, blocking=True):
        self.path = Path(path)
        self.blocking = blocking
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        self.handle = os.fdopen(fd, "r+b", buffering=0)
        # Windows byte-range locking requires an existing byte.
        if os.fstat(fd).st_size == 0:
            self.handle.write(b"\0")
        try:
            while True:
                try:
                    self.handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self.handle
                except OSError as exc:
                    if not self.blocking or (
                        exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                        and getattr(exc, "winerror", None) not in (33, 36)
                    ):
                        raise
                    time.sleep(0.1)
        except BaseException:
            self.handle.close()
            self.handle = None
            raise

    def __exit__(self, *exc):
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def _load(handle):
    handle.seek(1)
    raw = handle.read()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("expected object")
        # Reject non-finite or absurd persisted times instead of bypassing limits.
        for key in ("next_allowed", "cooldown_until", "stopped_at", "last_document_at"):
            number = float(value.get(key, 0))
            if not 0 <= number < 1e11:
                raise ValueError("invalid timestamp")
        for key in ("forbidden_streak", "file_forbidden", "page_forbidden", "document_html_streak"):
            if not 0 <= int(value.get(key, 0)) < 1000000:
                raise ValueError("invalid counter")
        return value
    except (ValueError, TypeError, UnicodeError) as exc:
        raise EisNetworkError("Повреждено состояние ограничителя ЕИС; запрос не отправлен") from exc


def _save(handle, state):
    handle.seek(1)
    handle.write(json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    handle.truncate()
    handle.flush()


class EisRuntime:
    def __init__(self, state_dir=None, interval=3.0, jitter=0.5, clock=None, sleep=None):
        self.state_dir = Path(state_dir) if state_dir is not None else application_data_dir()
        self.interval = max(0.0, float(interval))
        self.jitter = max(0.0, float(jitter))
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.thread_lock = threading.RLock()
        self.forbidden_streak = 0
        self.reset_metrics()

    def reset_metrics(self):
        self.metrics = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "requests": 0, "statuses": {}, "retries": 0, "wait_seconds": 0.0,
            "network_errors": 0, "outcome": "running",
        }

    def wait(self, seconds):
        seconds = max(0.0, float(seconds))
        if seconds:
            if seconds >= 2:
                from tendercore.eis.protocol import phase
                phase(f"ЕИС: ожидание {seconds:.0f} с", "info")
            self.metrics["wait_seconds"] += seconds
            self.sleep(seconds)

    def raw_get(self, get, url, **kwargs):
        with self.thread_lock, FileLock(self.state_dir / "eis_transport.lock") as handle:
            state = _load(handle)
            now = self.clock()
            if float(state.get("cooldown_until", 0)) > now:
                raise EisStopError(state.get("reason", "Пауза ЕИС"), state["cooldown_until"], state.get("status"))
            self.wait(float(state.get("next_allowed", 0)) - now)
            self.metrics["requests"] += 1
            try:
                response = get(url, **kwargs)
                status = int(response.status_code)
                counts = self.metrics["statuses"]
                counts[str(status)] = counts.get(str(status), 0) + 1
                scope = "file_forbidden" if "filestore" in urlsplit(url).path.lower() else "page_forbidden"
                if status == 403:
                    state[scope] = int(state.get(scope, 0)) + 1
                elif status == 200:
                    state[scope] = 0
                self.forbidden_streak = state.get(scope, 0)
                return response
            except Exception:
                self.metrics["network_errors"] += 1
                raise
            finally:
                state["next_allowed"] = self.clock() + self.interval + random.uniform(0, self.jitter)
                _save(handle, state)

    def stop(self, reason, seconds, status=None):
        until = self.clock() + max(1.0, float(seconds))
        with self.thread_lock, FileLock(self.state_dir / "eis_transport.lock") as handle:
            state = _load(handle)
            state.update(cooldown_until=until, reason=str(reason), status=status, stopped_at=self.clock(), document_html_streak=0)
            # A fresh attempt after cooldown starts with a fresh streak.
            state["forbidden_streak"] = 0
            state["file_forbidden"] = 0
            state["page_forbidden"] = 0
            _save(handle, state)
        from tendercore.eis.protocol import phase
        phase(str(EisStopError(reason, until, status)), "pause")
        raise EisStopError(reason, until, status)

    def finish(self, outcome):
        self.metrics.update(outcome=outcome, finished_at=datetime.now(timezone.utc).isoformat())
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".eis_metrics_", dir=self.state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(self.metrics, out, ensure_ascii=False, indent=2)
            os.replace(temp, self.state_dir / "eis_last_run.json")
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)


_RUNTIMES = {}


def get_runtime(state_dir=None):
    path = Path(state_dir) if state_dir is not None else application_data_dir()
    key = str(path.resolve())
    if key not in _RUNTIMES:
        _RUNTIMES[key] = EisRuntime(path)
    return _RUNTIMES[key]


def exclusive_eis_run(data_dir):
    """Apply to both CLI entry points; clients share their runtime and pacing."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            runtime = get_runtime(data_dir())
            lock = FileLock(runtime.state_dir / "eis_run.lock", blocking=False)
            try:
                lock.__enter__()
            except OSError:
                print("ЕИС: уже выполняется выборка или анализ в этой папке. Второй запуск отменён.")
                raise SystemExit(75)
            runtime.reset_metrics()
            runtime.metrics["source"] = Path(function.__code__.co_filename).stem
            outcome = "completed"
            try:
                return function(*args, **kwargs)
            except EisStopError as exc:
                outcome = "paused"
                print(f"ЕИС: {exc}. Прогресс сохранён, новых запросов нет.")
                raise SystemExit(77)
            except BaseException:
                outcome = "interrupted"
                raise
            finally:
                try:
                    runtime.finish(outcome)
                except OSError as exc:
                    print(f"ЕИС: не удалось записать сетевую сводку: {type(exc).__name__}")
                lock.__exit__(None, None, None)
        return wrapped
    return decorate
