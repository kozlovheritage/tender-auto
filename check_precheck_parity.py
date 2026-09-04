import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
from tendercore.analysis.precheck import check_title

# (предмет, должен_ли_остановить) — берём реальные ctx из shadow_diff
cases = [
    ("Поставка продуктов питания (Рыба свежемороженая и кальмары)", True),
    ("поставка заменителей молока для кормления новорожденных", True),
    ("Приобретение электросварной трубы", True),
    ("Поставка полиэтиленовых труб", True),
    ("ОКПД2 25.11.10.000 Поставка блочно-модульного здания КПД для нужд филиала АО ДРСК", True),
    ("Поставка токарного станка с ЧПУ", False),  # контроль: не должно резаться
]

ok = 0
for subj, want in cases:
    res = check_title(subj)
    got = bool(res)
    mark = "OK  " if got == want else "FAIL"
    if got == want: ok += 1
    print(f"{mark} стоп={got!s:5} ждём={want!s:5} | {subj[:55]}")
    if res:
        print(f"       -> {res}")
print(f"\nИтог: {ok}/{len(cases)}")