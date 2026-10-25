# reset_decisions.py — удалить решения указанных дат (с бэкапом БД)
import sqlite3, shutil, sys, datetime, os

db = os.path.join("data", "decisions.db")
if not os.path.exists(db):
    print("❌ не найдена data/decisions.db — запускай из папки проекта")
    raise SystemExit(1)
bak = db + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(db, bak)
print("💾 бэкап:", os.path.basename(bak))
conn = sqlite3.connect(db)
print("решений по датам:")
for d, c in conn.execute("SELECT processed_date, COUNT(*) FROM decisions GROUP BY processed_date ORDER BY processed_date"):
    print(f"  {d}: {c}")
dates = sys.argv[1:] or [datetime.datetime.now().strftime("%Y-%m-%d")]
for d in dates:
    n = conn.execute("DELETE FROM decisions WHERE processed_date=?", (d,)).rowcount
    print(f"🗑 удалено {n} решений за {d}")
conn.commit()
conn.close()
print("Готово. Дальше: python tender_auto.py")