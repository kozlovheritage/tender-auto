# extend_catalog.py — щебень/песок/ЩПС/керамзит в каталог Цемторга (json + стоп-факторы)
import pathlib, json, re
NEW = [
    ("Щебень фракции 5-20", "ГОСТ 8267-93"),
    ("Щебень фракции 20-40", "ГОСТ 8267-93"),
    ("Щебень фракции 40-70", "ГОСТ 8267-93"),
    ("Отсев фракции 0-5", "ГОСТ 8267-93"),
    ("Щебеночно-песчаная смесь (ЩПС)", "ГОСТ 32826-2014"),
    ("Песок природный для строительных работ", "ГОСТ 8736-2014"),
    ("Песок строительный фракционированный", "ГОСТ 8736-2014"),
    ("Керамзитовый гравий / щебень", "ГОСТ 32496-2013"),
]
cat_p = pathlib.Path("profiles/cemtorg/catalog.json")
cat = json.loads(cat_p.read_text(encoding="utf-8"))
blob = json.dumps(cat, ensure_ascii=False)
added = 0
for name, gost in NEW:
    if name in blob:
        continue
    item = {"name": name, "gost": gost}
    if isinstance(cat, list):
        cat.append(item)
    elif isinstance(cat, dict):
        key = next((k for k in ("items", "positions", "catalog", "products") if isinstance(cat.get(k), list)), None)
        if key:
            cat[key].append(item)
        elif isinstance(cat.get("categories"), list):
            tgt = next((c for c in cat["categories"] if "неруд" in str(c.get("name", "")).lower() or "щеб" in str(c.get("name", "")).lower()), None)
            if tgt is None:
                tgt = {"name": "Нерудные материалы", "items": []}
                cat["categories"].append(tgt)
            tgt.setdefault("items", []).append(item)
        else:
            cat.setdefault("items", []).append(item)
    added += 1
cat_p.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"catalog.json: добавлено {added} позиций")
sf = pathlib.Path("profiles/cemtorg/stop_factors.txt")
txt = sf.read_text(encoding="utf-8")
lines = [f"- {n} ({g})" for n, g in NEW if n not in txt]
if lines:
    txt = txt.rstrip() + "\n# Расширение каталога (нерудные материалы):\n" + "\n".join(lines) + "\n"
    sf.write_text(txt, encoding="utf-8")
print(f"stop_factors.txt: дописано {len(lines)} строк каталога")