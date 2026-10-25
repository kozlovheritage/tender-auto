"""Offline, explicit scenario estimate; never changes qualification decisions."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re

ORIGIN = "Производство «Каменный цветок», д. Непецино, г.о. Коломна, Московская область"
DISCLAIMER = (
    "Сценарная оценка, не тариф перевозчика и не подтверждённая себестоимость. "
    "Километраж и расходы в демонстрационной таблице синтетические. "
    "Проверить маршрут, ограничения для грузовиков, погрузку и разгрузку."
)


def normalized(value):
    return re.sub(r"\s+", " ", str(value).lower().replace("ё", "е")).strip()


def delivery_address(response):
    """Keep the complete field, including continuation lines; don't guess a city."""
    lines = str(response or "").splitlines()
    collected = []
    taking = False
    for line in lines:
        if re.match(r"^\s*(?:---|#{1,6}\s)", line) and taking:
            break
        clean = re.sub(r"\*\*|__", "", line).strip()
        match = re.match(r"^(?:[-•]\s*)?(?:Адрес|Место)\s+поставки"
                         r"(?:\s+(?:товара|товаров|продукции))?(?:\s*\(адрес\))?\s*:\s*(.*)", clean, re.I)
        if match:
            if taking:
                collected.append(" / ")
            collected.append(match.group(1))
            taking = True
        elif taking:
            if re.match(r"^(?:[-•]\s*)?[^:]{1,70}:\s*", clean):
                break
            if clean:
                collected.append(clean)
    result = " ".join(collected).strip()
    if not result or re.search(r"информация отсутствует|не указан|не определ[её]н", result, re.I):
        return None
    return result


def number(value, name, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{name}: ожидается число, а не да/нет")
    try:
        result = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: неверное число") from None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f"{name}: требуется конечное {'положительное' if positive else 'неотрицательное'} число")
    return result


def money(value):
    return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}".replace(",", " ")


def calculate(one_way_km, config):
    """One vehicle round trip only; no guessed payload, trips, or density."""
    distance = number(one_way_km, "Километраж", positive=True)
    fuel_l = number(config["fuel_l_per_100km"], "Расход топлива", positive=True)
    fuel_price = number(config["fuel_rub_per_l"], "Цена топлива", positive=True)
    other = number(config["other_rub_per_km"], "Прочие расходы")
    fixed = number(config["fixed_rub_per_trip"], "Фиксированная часть")
    reserve = number(config["reserve_percent"], "Резерв")
    if reserve > 100:
        raise ValueError("Резерв не должен превышать 100%")
    run = distance * 2
    fuel = run * fuel_l / 100 * fuel_price
    operating = run * other
    subtotal = fuel + operating + fixed
    contingency = subtotal * reserve / 100
    return dict(distance=distance, run=run, fuel=fuel, operating=operating,
                fixed=fixed, reserve=contingency, total=subtotal + contingency)


def select_route(address, routes):
    """Require all route match terms, reject multiple possible route rows."""
    text = normalized(address)
    candidates = []
    for route in routes:
        terms = route.get("match_all", [])
        if not terms or not isinstance(terms, list) or any(not str(term).strip() for term in terms):
            raise ValueError("Маршрут должен иметь непустой список match_all")
        if all(re.search(r"(?<!\w)" + re.escape(normalized(term)) + r"(?!\w)", text)
               for term in terms):
            candidates.append(route)
    if len(candidates) != 1:
        return None, ("Найдено несколько направлений/вариантов маршрута; нужна проверка."
                      if candidates else "Нет подтверждённого километража для этого адреса в таблице маршрутов.")
    return candidates[0], None


def estimate(response, config_path):
    """All errors become explicit 'not calculated' rows, never fake zero costs."""
    address = delivery_address(response)
    result = {
        "title": "Предварительная оценка логистики",
        "rows": [("Точка отправления", ORIGIN),
                 ("Место поставки из аналитики", address or "Не найдено в отчёте"),
                 ("Транспорт", "Тягач MAN + бортовой полуприцеп; открытый/крытый — уточнить")],
        "warning": DISCLAIMER,
        "status": "Не рассчитано",
    }
    try:
        with Path(config_path).open(encoding="utf-8-sig") as handle:
            config = json.load(handle)
        if config.get("origin") != ORIGIN:
            raise ValueError("Точка отправления отличается от согласованного производства в Непецино")
        if not address:
            raise ValueError("Адрес поставки отсутствует или не определён")
        # Multiple explicit locations, an address list or 'по заявкам' must not
        # be priced as one destination, even if one table entry happens to match.
        # "д. 1" is a house number, not a second village ("д. Ивановка").
        locations = re.findall(r"(?:^|[,;\n])\s*(?:(?:г\.(?!\s*о\.)|д\.)\s*|"
                               r"(?:город|деревня|село|пос[её]лок)\s+)[^\W\d_][^,;\n]*",
                               address, re.I)
        if len(locations) > 1 or ";" in address or re.search(r"по заявкам|несколько адресов|различным адресам|по адресам|/\s*г\.", address, re.I):
            raise ValueError("Несколько мест поставки или поставка по заявкам: нужен отдельный расчёт маршрутов")
        route, reason = select_route(address, config.get("routes", []))
        if route is None:
            raise ValueError(reason)
        if not route.get("source") or not isinstance(route.get("synthetic"), bool):
            raise ValueError("У маршрута должны быть source и явный признак synthetic")
        values = calculate(route["one_way_km"], config)
        result["status"] = "Синтетический сценарий · один рейс"
        result["rows"].extend([
            ("Маршрут в таблице", route["label"]),
            ("Источник километража", route["source"]),
            ("Точность расстояния", "Синтетический пример, не построенный маршрут" if route["synthetic"]
             else "Вручную заданное расстояние; проверить перед участием"),
            ("Расстояние в одну сторону", f"{values['distance']} км"),
            ("Общий пробег", f"{values['run']} км = туда + порожний возврат"),
            ("Синтетические параметры",
             f"Расход {config['fuel_l_per_100km']} л/100 км; топливо {config['fuel_rub_per_l']} руб./л; "
             f"прочие расходы {config['other_rub_per_km']} руб./км; фиксированная часть "
             f"{config['fixed_rub_per_trip']} руб.; резерв {config['reserve_percent']}%."),
            ("Топливо", f"{money(values['fuel'])} руб. = пробег × расход / 100 × цена топлива"),
            ("Прочие расходы", f"{money(values['operating'])} руб. = пробег × ставка на км; "
             "условно включает водителя, обслуживание и износ, без повторного учёта топлива"),
            ("Фиксированная часть", f"{money(values['fixed'])} руб. — условные дополнительные расходы на рейс"),
            ("Резерв", f"{money(values['reserve'])} руб. = (топливо + прочие + фиксированная часть) × резерв / 100"),
            ("Ориентир за один рейс", f"≈ {money(values['total'])} руб. Синтетические ставки, не коммерческое предложение."),
            ("Вся поставка и число рейсов", "Не рассчитаны: грузоподъёмность, масса/объём и график партий "
             "не подтверждены. Нельзя считать эту сумму стоимостью доставки всего объёма."),
            ("Совместимость груза", "Проверить упаковку и способ погрузки/разгрузки. "
             "Для навалочных грузов бортовой полуприцеп не считать пригодным автоматически."),
        ])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["rows"].append(("Почему нет суммы", str(exc)))
    result["rows"].append(("Влияние на решение", "Расчёт справочный и не меняет решение аналитики."))
    return result
