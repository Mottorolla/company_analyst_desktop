from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from company_analyst.analytics import build_report
from company_analyst.dashboard import build_dashboard_charts, dashboard_records, dashboard_summary
from company_analyst.database import HistoryDB
from company_analyst.fns_source import FNSBFOClient
from company_analyst.main_window import MainWindow
from company_analyst.models import CompanyFinancials


ROOT = Path(__file__).resolve().parents[1]


def test_period_depth_labels_are_clear():
    assert [MainWindow.period_depth_label(years) for years in range(1, 8)] == [
        "1 год", "2 года", "3 года", "4 года", "5 лет", "6 лет", "7 лет"
    ]


class FakeClient(FNSBFOClient):
    def __init__(self):
        pass

    def search_company(self, inn: str):
        data = json.loads((ROOT / "sample_data" / "search_example.json").read_text(encoding="utf-8"))
        return data["content"][0]

    def fetch_reports(self, organization_id: int):
        return json.loads((ROOT / "sample_data" / "bfo_example.json").read_text(encoding="utf-8"))


def test_parse_company_year():
    row = FakeClient().fetch_company_year("5256038700", 2025)
    assert row.inn == "5256038700"
    assert row.name == 'ООО "ПРИМЕР"'
    assert row.revenue == 6390649
    assert row.net_profit == 45194
    assert row.assets == 14690266
    assert row.current_ratio is not None
    assert row.source_url.endswith("period=2025&detailId=54356540")


def test_parse_company_period_marks_missing_year():
    rows = FakeClient().fetch_company_years("5256038700", [2024, 2025])
    assert [row.year for row in rows] == [2024, 2025]
    assert rows[0].error
    assert not rows[1].error


def test_report_has_comparison():
    row = FakeClient().fetch_company_year("5256038700", 2025)
    report = build_report([row], "Тест", 2025)
    assert "СРАВНИТЕЛЬНЫЙ АНАЛИТИЧЕСКИЙ ОТЧЁТ" in report
    assert "чистая рентабельность" in report.lower()
    assert "ИНН 5256038700" in report


def test_report_has_multi_year_dynamics():
    current = FakeClient().fetch_company_year("5256038700", 2025)
    previous = replace(current, year=2024, revenue=current.revenue * 0.9, net_profit=current.net_profit * 0.8)
    report = build_report([previous, current], "Динамика", 2025)
    assert "Период анализа: 2024–2025" in report
    assert "Динамика за период" in report
    assert "среднегодовой темп" in report


def test_dashboard_data_and_export(tmp_path):
    first = FakeClient().fetch_company_year("5256038700", 2025)
    second = CompanyFinancials(
        name='АО "ВТОРОЙ ПРИМЕР"',
        inn="7700000000",
        year=2025,
        revenue=3_200_000,
        net_profit=-120_000,
        cost_sales=2_400_000,
        selling_expenses=150_000,
        admin_expenses=170_000,
        other_expenses=80_000,
        assets=5_000_000,
        current_assets=2_000_000,
        equity=1_600_000,
        shortterm_liabilities=1_100_000,
        longterm_liabilities=2_300_000,
    )
    rows = [first, second]
    records = dashboard_records(rows)
    assert len(records) == 2
    assert records[0]["Выручка"] == first.revenue / 1_000
    summary = dashboard_summary(rows)
    assert summary["companies"] == 2
    assert summary["profit"] == first.net_profit + second.net_profit

    previous_first = replace(first, year=2024, revenue=first.revenue * 0.9, net_profit=first.net_profit * 0.8)
    previous_second = replace(second, year=2024, revenue=second.revenue * 0.85, net_profit=-80_000)
    chart, components = build_dashboard_charts([previous_first, previous_second, first, second], "Выручка", 2025)
    assert len(components) == 9
    spec = chart.to_dict()
    assert len(spec["vconcat"]) == 5
    assert "Динамика выручки" in components
    output = tmp_path / "dashboard.png"
    chart.save(output, scale_factor=1)
    assert output.exists() and output.stat().st_size > 1_000


def test_history_database_migrates_and_keeps_period(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, year INTEGER NOT NULL, "
        "inns TEXT NOT NULL, created_at TEXT NOT NULL, report_text TEXT NOT NULL, data_json TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    db = HistoryDB(db_path)
    current = FakeClient().fetch_company_year("5256038700", 2025)
    previous = replace(current, year=2024)
    analysis_id = db.save("Период", 2025, [previous, current], "Отчёт")
    entry = db.list()[0]
    assert entry["period_start"] == 2024
    assert entry["period_end"] == 2025
    restored = db.get(analysis_id)
    assert restored is not None
    assert len(restored["rows"]) == 2
