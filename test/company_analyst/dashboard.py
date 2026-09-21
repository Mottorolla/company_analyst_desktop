from __future__ import annotations

import tempfile
from pathlib import Path
from statistics import median
from typing import Iterable

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .analytics import fmt_money, fmt_pct, fmt_ratio
from .altair_compat import load_altair
from .models import CompanyFinancials


DASHBOARD_STYLE = """
QWidget#dashboardRoot { background: #F4F7FB; color: #18212F; font-family: 'Segoe UI'; }
QFrame#dashboardHeader { background: #172033; border: none; }
QLabel#dashboardTitle { color: white; font-size: 20px; font-weight: 800; }
QLabel#dashboardSubtitle { color: #AFC0DD; }
QFrame#filterPanel, QFrame#kpiCard { background: white; border: 1px solid #DDE5F1; border-radius: 10px; }
QLabel#filterTitle { font-size: 14px; font-weight: 800; color: #172033; }
QLabel#kpiValue { font-size: 20px; font-weight: 800; color: #172033; }
QLabel#kpiCaption, QLabel#muted { color: #66748A; }
QPushButton { background: white; border: 1px solid #CFD8E8; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: #EFF4FC; }
QPushButton#primary { background: #315EFB; color: white; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #244BD2; }
QLineEdit, QComboBox, QListWidget { background: white; border: 1px solid #CFD8E8; border-radius: 7px; padding: 6px; }
QListWidget::item { padding: 7px; border-radius: 5px; }
QListWidget::item:selected { background: #DCE7FF; color: #18326D; }
QTabWidget::pane { border: 1px solid #DDE5F1; background: white; }
QTabBar::tab { background: #E8EDF5; padding: 9px 18px; }
QTabBar::tab:selected { background: white; color: #315EFB; font-weight: 700; }
QTableWidget { background: white; border: none; gridline-color: #E7ECF4; }
QHeaderView::section { background: #EEF2F8; border: none; padding: 8px; font-weight: 700; }
"""


METRICS = {
    "Выручка": "Выручка, млн ₽",
    "Чистая прибыль": "Чистая прибыль, млн ₽",
    "Активы": "Активы, млн ₽",
    "Капитал": "Капитал, млн ₽",
    "Расходы": "Расходы, млн ₽",
}


def _money_mln(value: float | None) -> float | None:
    # ГИР БО возвращает денежные строки формы в тысячах рублей.
    return None if value is None else value / 1_000.0


def dashboard_records(rows: Iterable[CompanyFinancials]) -> list[dict]:
    records: list[dict] = []
    for row in rows:
        if row.error:
            continue
        records.append(
            {
                "Компания": row.name,
                "ИНН": row.inn,
                "Год": row.year,
                "Выручка": _money_mln(row.revenue),
                "Чистая прибыль": _money_mln(row.net_profit),
                "Активы": _money_mln(row.assets),
                "Капитал": _money_mln(row.equity),
                "Расходы": _money_mln(row.total_expenses),
                "Себестоимость": _money_mln(abs(row.cost_sales)) if row.cost_sales is not None else None,
                "Коммерческие": _money_mln(abs(row.selling_expenses)) if row.selling_expenses is not None else None,
                "Управленческие": _money_mln(abs(row.admin_expenses)) if row.admin_expenses is not None else None,
                "Прочие": _money_mln(abs(row.other_expenses)) if row.other_expenses is not None else None,
                "Краткосрочные обязательства": _money_mln(row.shortterm_liabilities),
                "Долгосрочные обязательства": _money_mln(row.longterm_liabilities),
                "Чистая маржа": row.net_margin,
                "ROA": row.roa,
                "ROE": row.roe,
                "Текущая ликвидность": row.current_ratio,
                "D/E": row.debt_to_equity,
            }
        )
    return records


def dashboard_summary(rows: Iterable[CompanyFinancials]) -> dict[str, float | int | None]:
    valid = [row for row in rows if not row.error]
    margins = [row.net_margin for row in valid if row.net_margin is not None]
    return {
        "companies": len(valid),
        "revenue": sum(row.revenue or 0 for row in valid) if valid else None,
        "profit": sum(row.net_profit or 0 for row in valid) if valid else None,
        "margin": median(margins) if margins else None,
        "assets": sum(row.assets or 0 for row in valid) if valid else None,
    }


def _base_chart(data: list[dict]) -> alt.Chart:
    alt = load_altair()
    return alt.Chart(alt.Data(values=data))


def build_dashboard_charts(
    rows: list[CompanyFinancials],
    focus_metric: str,
    comparison_year: int | None = None,
) -> tuple[alt.Chart, dict[str, alt.Chart]]:
    alt = load_altair()
    all_data = dashboard_records(rows)
    if not all_data:
        empty = (
            alt.Chart(alt.Data(values=[{"message": "Нет данных для построения"}]))
            .mark_text(size=18, color="#66748A")
            .encode(text="message:N")
            .properties(width=900, height=420)
        )
        return empty, {"Пустой график": empty}

    years = sorted({int(record["Год"]) for record in all_data})
    comparison_year = comparison_year if comparison_year in years else years[-1]
    data = [record for record in all_data if int(record["Год"]) == comparison_year]

    company_pick = alt.selection_point(
        name="company_pick", fields=["Компания"], empty=True, on="click", toggle=True, clear="dblclick"
    )
    opacity = alt.condition(company_pick, alt.value(1.0), alt.value(0.18))

    revenue_trend = (
        _base_chart(all_data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=55), strokeWidth=2.5)
        .encode(
            x=alt.X("Год:O", title=None, axis=alt.Axis(labelAngle=0, gridColor="#EEF2F7")),
            y=alt.Y("Выручка:Q", title="млн ₽", axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            color=alt.Color("Компания:N", title=None),
            opacity=opacity,
            tooltip=[
                alt.Tooltip("Компания:N"), alt.Tooltip("ИНН:N"), alt.Tooltip("Год:O"),
                alt.Tooltip("Выручка:Q", title="Выручка, млн ₽", format=",.2f"),
            ],
        )
        .properties(title="Динамика выручки", width=430, height=250)
    )

    profit_trend = (
        _base_chart(all_data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=55), strokeWidth=2.5)
        .encode(
            x=alt.X("Год:O", title=None, axis=alt.Axis(labelAngle=0, gridColor="#EEF2F7")),
            y=alt.Y("Чистая прибыль:Q", title="млн ₽", axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            color=alt.Color("Компания:N", title=None),
            opacity=opacity,
            tooltip=[
                alt.Tooltip("Компания:N"), alt.Tooltip("ИНН:N"), alt.Tooltip("Год:O"),
                alt.Tooltip("Чистая прибыль:Q", title="Прибыль / убыток, млн ₽", format=",.2f"),
            ],
        )
        .properties(title="Динамика чистой прибыли / убытка", width=430, height=250)
    )

    margin_trend = (
        _base_chart(all_data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=55), strokeWidth=2.5)
        .encode(
            x=alt.X("Год:O", title=None, axis=alt.Axis(labelAngle=0, gridColor="#EEF2F7")),
            y=alt.Y("Чистая маржа:Q", title="%", axis=alt.Axis(gridColor="#E8EDF5")),
            color=alt.Color("Компания:N", title=None),
            opacity=opacity,
            tooltip=[
                alt.Tooltip("Компания:N"), alt.Tooltip("ИНН:N"), alt.Tooltip("Год:O"),
                alt.Tooltip("Чистая маржа:Q", title="Чистая маржа, %", format=".2f"),
            ],
        )
        .properties(title="Динамика чистой рентабельности", width=920, height=230)
    )
    ranking = (
        _base_chart(data)
        .mark_bar(cornerRadiusEnd=5, color="#315EFB")
        .encode(
            x=alt.X(f"{focus_metric}:Q", title=METRICS[focus_metric], axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            y=alt.Y("Компания:N", sort="-x", title=None, axis=alt.Axis(labelLimit=190)),
            opacity=opacity,
            tooltip=[
                alt.Tooltip("Компания:N"), alt.Tooltip("ИНН:N"),
                alt.Tooltip(f"{focus_metric}:Q", title=METRICS[focus_metric], format=",.2f"),
            ],
        )
        .add_params(company_pick)
        .properties(title={"text": f"{METRICS[focus_metric]} · {comparison_year}", "subtitle": "Клик — подсветить компанию, двойной клик — сбросить"}, width=430, height=260)
    )

    profit = (
        _base_chart(data)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            x=alt.X("Чистая прибыль:Q", title="млн ₽", axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            y=alt.Y("Компания:N", sort="-x", title=None, axis=alt.Axis(labelLimit=190)),
            color=alt.condition(alt.datum["Чистая прибыль"] >= 0, alt.value("#16A06A"), alt.value("#E24A5A")),
            opacity=opacity,
            tooltip=[
                alt.Tooltip("Компания:N"), alt.Tooltip("ИНН:N"),
                alt.Tooltip("Чистая прибыль:Q", title="Прибыль / убыток, млн ₽", format=",.2f"),
            ],
        )
        .properties(title="Чистая прибыль / убыток", width=430, height=260)
    )

    expense_fields = ["Себестоимость", "Коммерческие", "Управленческие", "Прочие"]
    expenses = (
        _base_chart(data)
        .transform_fold(expense_fields, as_=["Статья", "Значение"])
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("Значение:Q", title="млн ₽", axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            y=alt.Y("Компания:N", title=None, axis=alt.Axis(labelLimit=190)),
            color=alt.Color(
                "Статья:N", title=None,
                scale=alt.Scale(domain=expense_fields, range=["#5677D9", "#8B6FD6", "#D26AA5", "#E7984C"]),
            ),
            opacity=opacity,
            tooltip=[alt.Tooltip("Компания:N"), alt.Tooltip("Статья:N"), alt.Tooltip("Значение:Q", title="млн ₽", format=",.2f")],
        )
        .properties(title="Структура расходов", width=430, height=270)
    )

    structure_fields = ["Активы", "Капитал", "Краткосрочные обязательства", "Долгосрочные обязательства"]
    structure = (
        _base_chart(data)
        .transform_fold(structure_fields, as_=["Показатель", "Значение"])
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("Значение:Q", title="млн ₽", axis=alt.Axis(format="~s", gridColor="#E8EDF5")),
            y=alt.Y("Компания:N", title=None, axis=alt.Axis(labelLimit=190)),
            color=alt.Color(
                "Показатель:N", title=None,
                scale=alt.Scale(domain=structure_fields, range=["#315EFB", "#16A06A", "#F0A43A", "#E24A5A"]),
            ),
            opacity=opacity,
            tooltip=[alt.Tooltip("Компания:N"), alt.Tooltip("Показатель:N"), alt.Tooltip("Значение:Q", title="млн ₽", format=",.2f")],
        )
        .properties(title="Баланс и источники финансирования", width=430, height=270)
    )

    profitability_fields = ["Чистая маржа", "ROA", "ROE"]
    profitability = (
        _base_chart(data)
        .transform_fold(profitability_fields, as_=["Коэффициент", "Значение"])
        .mark_circle(size=105, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Значение:Q", title="%", axis=alt.Axis(gridColor="#E8EDF5")),
            y=alt.Y("Компания:N", title=None, axis=alt.Axis(labelLimit=190)),
            color=alt.Color("Коэффициент:N", title=None, scale=alt.Scale(range=["#315EFB", "#16A06A", "#8B6FD6"])),
            opacity=opacity,
            tooltip=[alt.Tooltip("Компания:N"), alt.Tooltip("Коэффициент:N"), alt.Tooltip("Значение:Q", title="Значение, %", format=".2f")],
        )
        .properties(title="Рентабельность", width=430, height=260)
    )

    ratio_fields = ["Чистая маржа", "ROA", "ROE", "Текущая ликвидность", "D/E"]
    heatmap_base = (
        _base_chart(data)
        .transform_fold(ratio_fields, as_=["Коэффициент", "Значение"])
        .encode(
            x=alt.X("Коэффициент:N", title=None, axis=alt.Axis(labelAngle=-25)),
            y=alt.Y("Компания:N", title=None, axis=alt.Axis(labelLimit=190)),
            opacity=opacity,
            tooltip=[alt.Tooltip("Компания:N"), alt.Tooltip("Коэффициент:N"), alt.Tooltip("Значение:Q", format=".2f")],
        )
    )
    heatmap = (
        heatmap_base.mark_rect(cornerRadius=3)
        .encode(color=alt.Color("Значение:Q", title="Значение", scale=alt.Scale(scheme="redyellowgreen", domainMid=0)))
        + heatmap_base.mark_text(fontSize=10).encode(
            text=alt.Text("Значение:Q", format=".2f"),
            color=alt.condition(alt.datum["Значение"] > 35, alt.value("white"), alt.value("#1D2635")),
        )
    ).properties(title="Матрица финансовых коэффициентов", width=430, height=260)

    combined = (
        alt.vconcat(
            alt.hconcat(revenue_trend, profit_trend, spacing=28),
            margin_trend,
            alt.hconcat(ranking, profit, spacing=28),
            alt.hconcat(expenses, structure, spacing=28),
            alt.hconcat(profitability, heatmap, spacing=28),
            spacing=28,
        )
        .resolve_scale(color="independent")
        .configure(background="#FFFFFF")
        .configure_view(stroke=None)
        .configure_title(anchor="start", color="#172033", fontSize=15, fontWeight=700, subtitleColor="#66748A")
        .configure_axis(labelColor="#566277", titleColor="#566277", domainColor="#C9D3E3", tickColor="#C9D3E3")
        .configure_legend(labelColor="#566277", titleColor="#172033", orient="bottom")
    )
    components = {
        "Динамика выручки": revenue_trend.add_params(company_pick),
        "Динамика чистой прибыли": profit_trend.add_params(company_pick),
        "Динамика чистой рентабельности": margin_trend.add_params(company_pick),
        METRICS[focus_metric]: ranking,
        "Чистая прибыль / убыток": profit.add_params(company_pick),
        "Структура расходов": expenses.add_params(company_pick),
        "Баланс и источники финансирования": structure.add_params(company_pick),
        "Рентабельность": profitability.add_params(company_pick),
        "Матрица коэффициентов": heatmap.add_params(company_pick),
    }
    return combined, components


class KpiCard(QFrame):
    def __init__(self, caption: str):
        super().__init__()
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        label = QLabel(caption)
        label.setObjectName("kpiCaption")
        layout.addWidget(self.value)
        layout.addWidget(label)


class DashboardWindow(QWidget):
    def __init__(self, rows: list[CompanyFinancials], analysis_name: str, year: int, parent=None):
        super().__init__(parent, Qt.Window)
        self.rows = [row for row in rows if not row.error]
        self.analysis_name = analysis_name
        self.years = sorted({row.year for row in self.rows if row.year}) or [year]
        self.year = self.years[-1]
        self.period = str(self.years[0]) if len(self.years) == 1 else f"{self.years[0]}–{self.years[-1]}"
        self.current_chart: alt.Chart | None = None
        self.component_charts: dict[str, alt.Chart] = {}
        self._temporary_dir = tempfile.TemporaryDirectory(prefix="company_analyst_dashboard_")
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(180)
        self._refresh_timer.timeout.connect(self.refresh_dashboard)

        self.setObjectName("dashboardRoot")
        self.setStyleSheet(DASHBOARD_STYLE)
        self.setWindowTitle(f"BI-дашборд — {analysis_name} ({self.period})")
        self.resize(1500, 940)
        self.setMinimumSize(1120, 720)
        self._build_ui()
        self._select_all_companies()
        self.refresh_dashboard()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("dashboardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 12, 22, 12)
        headings = QVBoxLayout()
        title = QLabel(f"Финансовый BI-дашборд · {self.analysis_name}")
        title.setObjectName("dashboardTitle")
        subtitle = QLabel(f"Период: {self.period} · интерактивная аналитика Altair / Vega-Lite")
        subtitle.setObjectName("dashboardSubtitle")
        headings.addWidget(title)
        headings.addWidget(subtitle)
        header_layout.addLayout(headings)
        header_layout.addStretch()

        self.save_png_btn = QPushButton("Сохранить дашборд PNG")
        self.save_png_btn.setObjectName("primary")
        self.save_svg_btn = QPushButton("SVG")
        self.save_html_btn = QPushButton("Интерактивный HTML")
        self.copy_btn = QPushButton("Копировать изображение")
        self.save_png_btn.clicked.connect(self.save_dashboard_png)
        self.save_svg_btn.clicked.connect(self.save_dashboard_svg)
        self.save_html_btn.clicked.connect(self.save_dashboard_html)
        self.copy_btn.clicked.connect(self.copy_dashboard_image)
        for button in (self.save_png_btn, self.save_svg_btn, self.save_html_btn, self.copy_btn):
            header_layout.addWidget(button)
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_filter_panel())
        splitter.addWidget(self._build_content_panel())
        splitter.setSizes([270, 1220])
        root.addWidget(splitter, 1)

    def _build_filter_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("filterPanel")
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 18)

        title = QLabel("Фильтры")
        title.setObjectName("filterTitle")
        layout.addWidget(title)
        year_label = QLabel(f"Период динамики: {self.period}")
        year_label.setObjectName("muted")
        layout.addWidget(year_label)
        layout.addWidget(QLabel("Год сравнительного среза"))
        self.comparison_year_combo = QComboBox()
        for selected_year in reversed(self.years):
            self.comparison_year_combo.addItem(str(selected_year), selected_year)
        self.comparison_year_combo.currentIndexChanged.connect(lambda _index: self._refresh_timer.start())
        layout.addWidget(self.comparison_year_combo)
        layout.addSpacing(8)

        layout.addWidget(QLabel("Поиск компании"))
        self.company_search = QLineEdit()
        self.company_search.setPlaceholderText("Название или ИНН…")
        self.company_search.textChanged.connect(self._filter_company_list)
        layout.addWidget(self.company_search)

        layout.addWidget(QLabel("Компании"))
        self.company_list = QListWidget()
        self.company_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        latest_by_inn: dict[str, CompanyFinancials] = {}
        for row in self.rows:
            if row.inn not in latest_by_inn or row.year > latest_by_inn[row.inn].year:
                latest_by_inn[row.inn] = row
        for row in latest_by_inn.values():
            item = QListWidgetItem(f"{row.name}\nИНН {row.inn}")
            item.setData(Qt.UserRole, row.inn)
            item.setToolTip(row.name)
            self.company_list.addItem(item)
        self.company_list.itemSelectionChanged.connect(lambda: self._refresh_timer.start())
        layout.addWidget(self.company_list, 1)

        select_row = QHBoxLayout()
        select_all = QPushButton("Все")
        clear_all = QPushButton("Снять")
        select_all.clicked.connect(self._select_all_companies)
        clear_all.clicked.connect(self.company_list.clearSelection)
        select_row.addWidget(select_all)
        select_row.addWidget(clear_all)
        layout.addLayout(select_row)

        self.selected_label = QLabel()
        self.selected_label.setObjectName("muted")
        layout.addWidget(self.selected_label)
        layout.addSpacing(10)

        layout.addWidget(QLabel("Главный показатель"))
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(METRICS.keys())
        self.metric_combo.currentTextChanged.connect(lambda _text: self._refresh_timer.start())
        layout.addWidget(self.metric_combo)

        layout.addWidget(QLabel("Экспорт отдельного графика"))
        self.component_combo = QComboBox()
        layout.addWidget(self.component_combo)
        component_save = QPushButton("Сохранить выбранный PNG")
        component_save.clicked.connect(self.save_component_png)
        layout.addWidget(component_save)

        tip = QLabel("Кликните по столбцу главного графика, чтобы связанная подсветка применилась ко всему дашборду. Двойной клик сбрасывает выбор.")
        tip.setWordWrap(True)
        tip.setObjectName("muted")
        layout.addSpacing(10)
        layout.addWidget(tip)
        return panel

    def _build_content_panel(self) -> QWidget:
        # Отложенный импорт позволяет запускать офлайн-тесты аналитики в
        # headless-средах без системных библиотек Chromium/Qt WebEngine.
        from PySide6.QtWebEngineWidgets import QWebEngineView

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        kpis = QHBoxLayout()
        self.kpi_companies = KpiCard("Компаний в выборке")
        self.kpi_revenue = KpiCard("Совокупная выручка")
        self.kpi_profit = KpiCard("Чистая прибыль / убыток")
        self.kpi_margin = KpiCard("Медианная маржа")
        self.kpi_assets = KpiCard("Совокупные активы")
        for card in (self.kpi_companies, self.kpi_revenue, self.kpi_profit, self.kpi_margin, self.kpi_assets):
            kpis.addWidget(card, 1)
        layout.addLayout(kpis)

        self.tabs = QTabWidget()
        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.tabs.addTab(self.web_view, "Дашборд")
        self.ratio_table = QTableWidget()
        self.ratio_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ratio_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.ratio_table, "Таблица коэффициентов")
        layout.addWidget(self.tabs, 1)
        return panel

    def _filter_company_list(self, query: str) -> None:
        needle = query.strip().lower()
        for index in range(self.company_list.count()):
            item = self.company_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _select_all_companies(self) -> None:
        for index in range(self.company_list.count()):
            self.company_list.item(index).setSelected(True)

    def _selected_rows(self) -> list[CompanyFinancials]:
        selected_inns = {item.data(Qt.UserRole) for item in self.company_list.selectedItems()}
        return [row for row in self.rows if row.inn in selected_inns]

    def refresh_dashboard(self) -> None:
        selected = self._selected_rows()
        comparison_year = int(self.comparison_year_combo.currentData())
        snapshot = [row for row in selected if row.year == comparison_year]
        self.selected_label.setText(f"Выбрано компаний: {len({row.inn for row in selected})} из {self.company_list.count()}")
        self._update_kpis(snapshot)
        self._update_ratio_table(snapshot)
        self.current_chart, self.component_charts = build_dashboard_charts(
            selected,
            self.metric_combo.currentText(),
            comparison_year,
        )

        old_component = self.component_combo.currentText()
        self.component_combo.blockSignals(True)
        self.component_combo.clear()
        self.component_combo.addItems(self.component_charts.keys())
        if old_component:
            index = self.component_combo.findText(old_component)
            if index >= 0:
                self.component_combo.setCurrentIndex(index)
        self.component_combo.blockSignals(False)

        html_path = Path(self._temporary_dir.name) / "dashboard.html"
        try:
            self.current_chart.save(html_path, inline=True, embed_options={"actions": False, "renderer": "svg"})
            self.web_view.load(QUrl.fromLocalFile(str(html_path.resolve())))
        except Exception as exc:
            self.web_view.setHtml(f"<h3>Не удалось построить дашборд</h3><p>{str(exc)}</p>")

    def _update_kpis(self, rows: list[CompanyFinancials]) -> None:
        summary = dashboard_summary(rows)
        self.kpi_companies.value.setText(str(summary["companies"]))
        self.kpi_revenue.value.setText(fmt_money(summary["revenue"]))
        self.kpi_profit.value.setText(fmt_money(summary["profit"]))
        self.kpi_margin.value.setText(fmt_pct(summary["margin"]))
        self.kpi_assets.value.setText(fmt_money(summary["assets"]))
        profit = summary["profit"]
        self.kpi_profit.value.setStyleSheet(f"color: {'#16A06A' if profit is not None and profit >= 0 else '#E24A5A'};")

    def _update_ratio_table(self, rows: list[CompanyFinancials]) -> None:
        headers = ["Компания", "ИНН", "Год", "Маржа", "ROA", "ROE", "Текущая ликвидность", "D/E", "Оборачиваемость активов"]
        self.ratio_table.setColumnCount(len(headers))
        self.ratio_table.setHorizontalHeaderLabels(headers)
        self.ratio_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.name, row.inn, str(row.year), fmt_pct(row.net_margin), fmt_pct(row.roa), fmt_pct(row.roe),
                fmt_ratio(row.current_ratio), fmt_ratio(row.debt_to_equity), fmt_ratio(row.asset_turnover),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.ratio_table.setItem(row_index, column, item)
        self.ratio_table.resizeColumnsToContents()
        self.ratio_table.horizontalHeader().setStretchLastSection(True)

    def _default_path(self, suffix: str, extra: str = "dashboard") -> str:
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in self.analysis_name).strip() or "analysis"
        return str(Path.home() / f"{safe_name}_{self.period}_{extra}.{suffix}")

    def _save_chart(self, chart: alt.Chart | None, caption: str, suffix: str, file_filter: str, **kwargs) -> None:
        if chart is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, caption, self._default_path(suffix), file_filter)
        if not path:
            return
        if not path.lower().endswith(f".{suffix}"):
            path += f".{suffix}"
        try:
            chart.save(path, **kwargs)
            QMessageBox.information(self, "Готово", f"Файл сохранён:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось сохранить файл:\n{exc}")

    def save_dashboard_png(self) -> None:
        self._save_chart(self.current_chart, "Сохранить дашборд PNG", "png", "PNG (*.png)", scale_factor=2)

    def save_dashboard_svg(self) -> None:
        self._save_chart(self.current_chart, "Сохранить дашборд SVG", "svg", "SVG (*.svg)")

    def save_dashboard_html(self) -> None:
        self._save_chart(
            self.current_chart,
            "Сохранить интерактивный HTML",
            "html",
            "HTML (*.html)",
            inline=True,
            embed_options={"actions": True, "renderer": "svg"},
        )

    def save_component_png(self) -> None:
        chart = self.component_charts.get(self.component_combo.currentText())
        self._save_chart(chart, "Сохранить выбранный график PNG", "png", "PNG (*.png)", scale_factor=2)

    def copy_dashboard_image(self) -> None:
        if self.current_chart is None:
            return
        path = Path(self._temporary_dir.name) / "clipboard_dashboard.png"
        try:
            self.current_chart.save(path, scale_factor=2)
            image = QImage(str(path))
            if image.isNull():
                raise RuntimeError("созданное изображение не удалось прочитать")
            QApplication.clipboard().setImage(image)
            QMessageBox.information(self, "Готово", "Изображение дашборда скопировано в буфер обмена.")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось скопировать изображение:\n{exc}")

    def closeEvent(self, event) -> None:  # noqa: N802 - имя Qt API
        self._temporary_dir.cleanup()
        super().closeEvent(event)
