"""CLI поверх tendercore: validate-rfq + run (прогон)."""
import sys
from pathlib import Path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "validate-rfq":
        import argparse
        from tendercore.rfq.queue import load_queue, validate_entry, validate_queue
        ap = argparse.ArgumentParser(prog="tendercore validate-rfq")
        ap.add_argument("--queue", default=str(
            Path(__file__).resolve().parent.parent / "data" / "rfq_queue.json"))
        a = ap.parse_args(argv[1:])
        p = Path(a.queue)
        if not p.exists():
            print(f"⛔ Очередь не найдена: {p}")
            return 2
        valid, invalid = validate_queue(load_queue(p))
        print(f"✅ Валидных: {len(valid)}")
        for e in invalid:
            print(f"⛔ {e.get('tender_number', '?')}:")
            for pr in validate_entry(e):
                print(f"    • {pr}")
        return 1 if invalid else 0

    # Всё остальное — прогон
    from tendercore.pipeline import run
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())