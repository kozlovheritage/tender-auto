#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор ключей собственной сборки. Нужен личный секрет из окружения."""
import datetime
from license_client import _sign

if __name__ == "__main__":
    email = input("email клиента: ").strip()
    plan = input("тариф (month/half/year/enterprise) [year]: ").strip() or "year"
    days = int(input("дней [365]: ").strip() or 365)
    expiry = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
    print("\nКЛЮЧ:\n", _sign({"email": email, "plan": plan, "expiry": expiry, "hwid": ""}))