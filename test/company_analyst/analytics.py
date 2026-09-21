from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Iterable, Optional

from .models import CompanyFinancials


def fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "н/д"
    sign = "−" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:,.2f} млрд руб.".replace(",", " ")
    if v >= 1_000:
        return f"{sign}{v / 1_000:,.2f} млн руб.".replace(",", " ")
    return f"{sign}{v:,.0f} тыс. руб.".replace(",", " ")


def fmt_pct(v: Optional[float]) -> str:
    return "н/д" if v is None else f"{v:.1f}%"


def fmt_ratio(v: Optional[float]) -> str:
    return "н/д" if v is None else f"{v:.2f}"


def _avg(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return mean(vals) if vals else None


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return median(vals) if vals else None


def _best(rows: list[CompanyFinancials], attr: str) -> CompanyFinancials | None:
    filtered = [row for row in rows if getattr(row, attr) is not None]
    return max(filtered, key=lambda row: getattr(row, attr)) if filtered else None


def _change_pct(first: Optional[float], last: Optional[float]) -> Optional[float]:
    if first in (None, 0) or last is None:
        return None
    return (last / first - 1.0) * 100.0


def _cagr(first: Optional[float], last: Optional[float], periods: int) -> Optional[float]:
    if first is None or last is None or first <= 0 or last < 0 or periods <= 0:
        return None
    return ((last / first) ** (1.0 / periods) - 1.0) * 100.0


def build_report(rows: list[CompanyFinancials], analysis_name: str, year: int) -> str:
    all_valid = [row for row in rows if not row.error]
    errors = [row for row in rows if row.error]
    years = sorted({row.year for row in rows if row.year})
    available_years = sorted({row.year for row in all_valid if row.year})
    snapshot_year = year if year in available_years else (available_years[-1] if available_years else year)
    valid = [row for row in all_valid if row.year == snapshot_year]
    requested_companies = {row.inn for row in rows}

    lines: list[str] = [f"СРАВНИТЕЛЬНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЁТ — {analysis_name}"]
    if len(years) > 1:
        lines.append(f"Период анализа: {years[0]}–{years[-1]}")
        lines.append(f"Год сравнительного среза: {snapshot_year}")
    else:
        lines.append(f"Отчётный год: {snapshot_year}")
    lines.append(f"Компаний со срезом за {snapshot_year} год: {len(valid)} из {len(requested_companies)}")
    lines.append("")

    if not valid:
        lines.append("Нет компаний с доступной бухгалтерской отчётностью для расчёта показателей.")
        if errors:
            lines.append("")
            lines.append("Ошибки загрузки:")
            for row in errors:
                lines.append(f"• ИНН {row.inn}, {row.year}: {row.error}")
        return "\n".join(lines)

    lines.append(f"1. Сводные показатели за {snapshot_year} год")
    revenue_values = [row.revenue for row in valid if row.revenue is not None]
    profit_values = [row.net_profit for row in valid if row.net_profit is not None]
    lines.append(f"Совокупная выручка: {fmt_money(sum(revenue_values) if revenue_values else None)}")
    lines.append(f"Совокупная чистая прибыль/убыток: {fmt_money(sum(profit_values) if profit_values else None)}")
    lines.append(f"Средняя чистая рентабельность: {fmt_pct(_avg(row.net_margin for row in valid))}")
    lines.append(f"Медианная чистая рентабельность: {fmt_pct(_median(row.net_margin for row in valid))}")
    lines.append("")

    revenue_leader = _best(valid, "revenue")
    profit_leader = _best(valid, "net_profit")
    margin_leader = _best([row for row in valid if row.net_margin is not None], "net_margin")
    liquidity_leader = _best([row for row in valid if row.current_ratio is not None], "current_ratio")

    lines.append("2. Сравнение компаний")
    if revenue_leader:
        lines.append(f"• Наибольшая выручка: {revenue_leader.name} — {fmt_money(revenue_leader.revenue)}.")
    if profit_leader:
        lines.append(f"• Наибольший финансовый результат: {profit_leader.name} — {fmt_money(profit_leader.net_profit)}.")
    if margin_leader:
        lines.append(f"• Максимальная чистая рентабельность: {margin_leader.name} — {fmt_pct(margin_leader.net_margin)}.")
    if liquidity_leader:
        lines.append(f"• Наибольшая текущая ликвидность: {liquidity_leader.name} — {fmt_ratio(liquidity_leader.current_ratio)}.")
    lines.append("")

    section = 3
    if len(available_years) > 1:
        lines.append(f"{section}. Динамика за период")
        grouped: dict[str, list[CompanyFinancials]] = defaultdict(list)
        for row in all_valid:
            grouped[row.inn].append(row)
        for company_rows in grouped.values():
            ordered = sorted(company_rows, key=lambda row: row.year)
            first, last = ordered[0], ordered[-1]
            if first.year == last.year:
                lines.append(f"• {last.name}: доступен только один год ({last.year}), тренд не рассчитывается.")
                continue
            revenue_change = _change_pct(first.revenue, last.revenue)
            revenue_cagr = _cagr(first.revenue, last.revenue, last.year - first.year)
            profit_delta = None if first.net_profit is None or last.net_profit is None else last.net_profit - first.net_profit
            margin_delta = None if first.net_margin is None or last.net_margin is None else last.net_margin - first.net_margin
            details = [f"выручка {fmt_pct(revenue_change)} за {first.year}–{last.year}"]
            if revenue_cagr is not None:
                details.append(f"среднегодовой темп {fmt_pct(revenue_cagr)}")
            details.append(f"изменение чистой прибыли {fmt_money(profit_delta)}")
            if margin_delta is not None:
                details.append(f"изменение маржи {margin_delta:+.1f} п.п.")
            lines.append(f"• {last.name}: {', '.join(details)}.")
        lines.append("")
        section += 1

    lines.append(f"{section}. Финансовый профиль компаний за {snapshot_year} год")
    for row in sorted(valid, key=lambda item: (item.revenue is None, -(item.revenue or 0))):
        profitability = "прибыльная" if (row.net_profit or 0) > 0 else "убыточная" if (row.net_profit or 0) < 0 else "с нулевым результатом"
        if row.debt_to_equity is None:
            debt_comment = "н/д"
        elif row.debt_to_equity < 0:
            debt_comment = "отрицательный капитал; показатель требует осторожной трактовки"
        elif row.debt_to_equity <= 1:
            debt_comment = "долг не превышает капитал"
        elif row.debt_to_equity <= 2:
            debt_comment = "долговая нагрузка повышенная"
        else:
            debt_comment = "долговая нагрузка высокая"
        if row.current_ratio is None:
            liquidity_comment = "н/д"
        elif row.current_ratio >= 2:
            liquidity_comment = "высокий запас текущей ликвидности"
        elif row.current_ratio >= 1:
            liquidity_comment = "оборотные активы покрывают краткосрочные обязательства"
        else:
            liquidity_comment = "оборотные активы ниже краткосрочных обязательств"
        lines.append(
            f"• {row.name} (ИНН {row.inn}): выручка {fmt_money(row.revenue)}, чистый результат {fmt_money(row.net_profit)}, "
            f"чистая маржа {fmt_pct(row.net_margin)}, ROA {fmt_pct(row.roa)}, ROE {fmt_pct(row.roe)}, "
            f"текущая ликвидность {fmt_ratio(row.current_ratio)} ({liquidity_comment}), D/E {fmt_ratio(row.debt_to_equity)} "
            f"({debt_comment}). Компания {profitability}."
        )
    lines.append("")
    section += 1

    lines.append(f"{section}. Риски и сигналы за {snapshot_year} год")
    any_signal = False
    for row in valid:
        signals: list[str] = []
        if row.net_profit is not None and row.net_profit < 0:
            signals.append("чистый убыток")
        if row.current_ratio is not None and row.current_ratio < 1:
            signals.append("текущая ликвидность ниже 1")
        if row.equity is not None and row.equity < 0:
            signals.append("отрицательный собственный капитал")
        if row.debt_to_equity is not None and row.debt_to_equity > 2:
            signals.append("D/E выше 2")
        if row.revenue == 0:
            signals.append("нулевая выручка")
        if signals:
            any_signal = True
            lines.append(f"• {row.name}: {', '.join(signals)}.")
    if not any_signal:
        lines.append("• По выбранным автоматическим индикаторам выраженных сигналов не выявлено; это не заменяет due diligence.")
    lines.append("")
    section += 1

    lines.append(f"{section}. Методика")
    lines.append(
        "Сравнение компаний выполняется по последнему доступному годовому срезу, а динамика — по всем загруженным годам. "
        "Денежные показатели ФНС хранятся в тыс. руб. Чистая маржа = чистая прибыль / выручка; ROA = чистая прибыль / активы; "
        "ROE = чистая прибыль / капитал; текущая ликвидность = оборотные активы / краткосрочные обязательства; "
        "D/E = обязательства / капитал. Автоматический анализ требует отраслевой и контекстной проверки."
    )

    if errors:
        lines.append("")
        lines.append(f"{section + 1}. Недоступные периоды")
        for row in errors:
            lines.append(f"• ИНН {row.inn}, {row.year}: {row.error}")

    return "\n".join(lines)
