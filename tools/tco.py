#!/usr/bin/env python3
"""Калькулятор сукупної вартості володіння (TCO) системою відеоспостереження в авто.

Використання:
    python3 tools/tco.py                       # базовий сценарій (30 авто, 3 роки)
    python3 tools/tco.py --sedan 20 --suv 40 --van 40 --years 5
    python3 tools/tco.py --breakeven            # точка беззбитковості self-hosted

Усі вхідні цифри — оціночні орієнтири 2026 р. і задумані як параметри для заміни
на дані з реальних комерційних пропозицій.
"""
import argparse
from dataclasses import dataclass, field

USD_UAH = 42.0  # орієнтовний курс, змінюється параметром --rate


@dataclass
class Hardware:
    """Вартість заліза і монтажу на одиницю техніки, USD."""
    sedan: float
    suv: float
    van: float
    install_sedan: float
    install_suv: float
    install_van: float


@dataclass
class Scenario:
    name: str
    hw: Hardware
    sub_per_vehicle_month: float   # підписка на платформу, USD/авто/міс.
    sim_per_vehicle_month: float   # мобільний трафік, USD/авто/міс.
    storage_per_vehicle_month: float  # хмарне зберігання понад підписку
    platform_fixed_month: float = 0.0  # сервер/ліцензії, не залежить від к-сті авто
    staff_fte: float = 0.0             # частка ставки інженера на підтримку
    staff_cost_month: float = 2000.0   # повна вартість 1 FTE інженера, USD/міс.
    maintenance_rate: float = 0.10     # % від вартості заліза на рік (ремонт, заміни)
    hw_refresh_years: int = 5          # горизонт заміни обладнання
    notes: str = ""


def fleet_hw_capex(s: Scenario, n_sedan: int, n_suv: int, n_van: int) -> float:
    h = s.hw
    return (n_sedan * (h.sedan + h.install_sedan)
            + n_suv * (h.suv + h.install_suv)
            + n_van * (h.van + h.install_van))


def compute(s: Scenario, n_sedan: int, n_suv: int, n_van: int, years: int) -> dict:
    n = n_sedan + n_suv + n_van
    capex = fleet_hw_capex(s, n_sedan, n_suv, n_van)
    months = years * 12

    opex_sub = s.sub_per_vehicle_month * n * months
    opex_sim = s.sim_per_vehicle_month * n * months
    opex_sto = s.storage_per_vehicle_month * n * months
    opex_platform = s.platform_fixed_month * months
    opex_staff = s.staff_fte * s.staff_cost_month * months
    opex_maint = capex * s.maintenance_rate * years

    # довиклик капіталу, якщо горизонт довший за строк служби заліза
    refresh = capex * max(0, (years - 1) // s.hw_refresh_years)

    opex = opex_sub + opex_sim + opex_sto + opex_platform + opex_staff + opex_maint
    total = capex + refresh + opex
    return {
        "scenario": s.name,
        "vehicles": n,
        "capex": capex + refresh,
        "opex_subscription": opex_sub,
        "opex_sim": opex_sim,
        "opex_storage": opex_sto,
        "opex_platform": opex_platform,
        "opex_staff": opex_staff,
        "opex_maintenance": opex_maint,
        "opex_total": opex,
        "total": total,
        "per_vehicle_month": total / n / months if n else 0.0,
        "notes": s.notes,
    }


def build_scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="A. Західний SaaS (Samsara/Motive-клас)",
            hw=Hardware(sedan=0, suv=0, van=0,
                        install_sedan=50, install_suv=60, install_van=90),
            sub_per_vehicle_month=33.0,   # залізо зазвичай включене в підписку
            sim_per_vehicle_month=0.0,    # трафік у підписці
            storage_per_vehicle_month=0.0,
            maintenance_rate=0.0,
            notes="Залізо і трафік у підписці; контракт 3 роки; дані поза Україною.",
        ),
        Scenario(
            name="B. UA-інтегратор (Teltonika/Streamax + локальна платформа)",
            hw=Hardware(sedan=250, suv=420, van=700,
                        install_sedan=30, install_suv=45, install_van=80),
            sub_per_vehicle_month=7.0,    # ~290 ₴ платформа+сервіс
            sim_per_vehicle_month=3.0,    # ~125 ₴ за 3 ГБ M2M
            storage_per_vehicle_month=1.0,
            maintenance_rate=0.10,
            notes="Гарантія та монтаж на місці, оплата в ₴, підтримка українською.",
        ),
        Scenario(
            name="C. Self-hosted (Traccar/JT1078 + MinIO)",
            hw=Hardware(sedan=220, suv=380, van=620,
                        install_sedan=30, install_suv=45, install_van=80),
            sub_per_vehicle_month=0.0,
            sim_per_vehicle_month=3.0,
            storage_per_vehicle_month=0.8,
            platform_fixed_month=150.0,   # сервери, бекапи, канал
            staff_fte=0.25,               # 1/4 ставки інженера підтримки
            staff_cost_month=2000.0,
            maintenance_rate=0.12,
            notes="Ліцензій немає, але з'являється постійна стаття 'люди'.",
        ),
    ]


def fmt_usd(v: float) -> str:
    return f"{v:>12,.0f}"


def print_report(rows: list[dict], years: int, rate: float) -> None:
    print(f"\nГоризонт: {years} р.  |  Автопарк: {rows[0]['vehicles']} авто  |  курс {rate:.1f} ₴/$\n")
    header = f"{'Сценарій':<58}{'CAPEX,$':>13}{'OPEX,$':>13}{'РАЗОМ,$':>13}{'$/авто/міс':>13}{'₴/авто/міс':>13}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['scenario']:<58}{fmt_usd(r['capex'])}{fmt_usd(r['opex_total'])}"
              f"{fmt_usd(r['total'])}{r['per_vehicle_month']:>13,.1f}"
              f"{r['per_vehicle_month'] * rate:>13,.0f}")
    print()
    print("Деталізація OPEX, $:")
    sub = f"{'':<58}{'підписка':>13}{'SIM':>13}{'сховище':>13}{'платформа':>13}{'персонал':>13}{'ремонт':>13}"
    print(sub)
    print("-" * len(sub))
    for r in rows:
        print(f"{r['scenario']:<58}{fmt_usd(r['opex_subscription'])}{fmt_usd(r['opex_sim'])}"
              f"{fmt_usd(r['opex_storage'])}{fmt_usd(r['opex_platform'])}"
              f"{fmt_usd(r['opex_staff'])}{fmt_usd(r['opex_maintenance'])}")
    print()


def breakeven(years: int, rate: float) -> None:
    """За якого розміру автопарку self-hosted стає дешевшим за інтегратора / SaaS."""
    scen = {s.name[0]: s for s in build_scenarios()}
    print(f"\nТочка беззбитковості self-hosted (горизонт {years} р.),"
          " склад парку 1/3 седан : 1/3 SUV : 1/3 мікроавтобус\n")
    header = f"{'авто':>6}{'A. SaaS, $':>16}{'B. інтегратор, $':>20}{'C. self-hosted, $':>20}{'дешевший':>16}"
    print(header)
    print("-" * len(header))
    for n in (10, 20, 30, 50, 75, 100, 150, 200, 300):
        third = n // 3
        parts = (third, third, n - 2 * third)
        res = {k: compute(s, *parts, years)["total"] for k, s in scen.items()}
        best = min(res, key=res.get)
        print(f"{n:>6}{res['A']:>16,.0f}{res['B']:>20,.0f}{res['C']:>20,.0f}{best:>16}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sedan", type=int, default=10)
    p.add_argument("--suv", type=int, default=12)
    p.add_argument("--van", type=int, default=8)
    p.add_argument("--years", type=int, default=3)
    p.add_argument("--rate", type=float, default=USD_UAH, help="курс ₴/$")
    p.add_argument("--breakeven", action="store_true",
                   help="показати таблицю точки беззбитковості замість базового звіту")
    a = p.parse_args()

    if a.breakeven:
        breakeven(a.years, a.rate)
        return

    rows = [compute(s, a.sedan, a.suv, a.van, a.years) for s in build_scenarios()]
    print_report(rows, a.years, a.rate)
    for r in rows:
        print(f"  · {r['scenario']}: {r['notes']}")
    print()


if __name__ == "__main__":
    main()
