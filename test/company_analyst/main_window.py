from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Signal, Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from .analytics import build_report
from .dashboard import DashboardWindow
from .database import HistoryDB
from .fns_source import FNSBFOClient
from .models import CompanyFinancials
from .report_dialog import ReportWindow


APP_STYLE = """
QMainWindow, QWidget { background: #f5f7fb; color: #172033; font-family: 'Segoe UI'; font-size: 13px; }
QFrame#topBar { background: #172033; border: none; }
QPushButton#navButton { color: #dce4f2; background: transparent; border: none; padding: 14px 18px; font-weight: 600; }
QPushButton#navButton:checked { color: white; background: #2b3852; border-bottom: 3px solid #7da2ff; }
QPushButton#primary { background: #315efb; color: white; border: none; border-radius: 7px; padding: 10px 18px; font-weight: 700; }
QPushButton#primary:hover { background: #244bd2; }
QPushButton { background: white; border: 1px solid #d5dbea; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #eef2fb; }
QPushButton:disabled { color: #9ca6b8; background: #edf0f5; }
QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #cfd7e8; border-radius: 7px; padding: 8px; min-height: 20px; }
QTableWidget { background: white; border: 1px solid #dfe4ef; border-radius: 8px; gridline-color: #e9edf5; }
QHeaderView::section { background: #eef2f8; border: none; border-right: 1px solid #dfe4ef; padding: 8px; font-weight: 700; }
QLabel#pageTitle { font-size: 24px; font-weight: 800; color: #172033; }
QLabel#subtitle { color: #647089; }
QLabel#dashboardTitle, QLabel#reportTitle { font-size: 18px; font-weight: 800; }
QProgressBar { background: #e7ebf3; border: none; border-radius: 5px; min-height: 9px; max-height: 9px; }
QProgressBar::chunk { background: #315efb; border-radius: 5px; }
"""


TABLE_COLUMNS = [
    ("Компания", "name"),
    ("ИНН", "inn"),
    ("Год", "year"),
    ("Выручка", "revenue"),
    ("Себестоимость", "cost_sales"),
    ("Прибыль / убыток", "net_profit"),
    ("Убыток", "loss"),
    ("Расходы", "total_expenses"),
    ("Активы", "assets"),
    ("Капитал", "equity"),
    ("Кратк. обяз.", "shortterm_liabilities"),
    ("Долгоср. обяз.", "longterm_liabilities"),
    ("Маржа", "net_margin"),
    ("ROA", "roa"),
    ("ROE", "roe"),
    ("Текущ. ликв.", "current_ratio"),
    ("D/E", "debt_to_equity"),
    ("ОКВЭД", "okved"),
    ("Регион", "region"),
    ("Статус", "status"),
    ("Источник", "source_url"),
]


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        root = Path(os.getenv("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path.home() / ".local" / "share"
    path = root / "CompanyAnalyst"
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_table_value(attr: str, value):
    if value is None:
        return "—"
    if attr in {"revenue", "cost_sales", "net_profit", "loss", "total_expenses", "assets", "equity", "shortterm_liabilities", "longterm_liabilities"}:
        return f"{value:,.0f}".replace(",", " ")
    if attr in {"net_margin", "roa", "roe"}:
        return f"{value:.1f}%"
    if attr in {"current_ratio", "debt_to_equity"}:
        return f"{value:.2f}"
    return str(value)


class FetchThread(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)

    def __init__(self, inns: list[str], years: list[int], timeout: int):
        super().__init__()
        self.inns = inns
        self.years = years
        self.timeout = timeout

    def run(self):
        client = FNSBFOClient(timeout=self.timeout)
        rows: list[CompanyFinancials] = []
        total = len(self.inns)
        for idx, inn in enumerate(self.inns, start=1):
            period = str(self.years[0]) if len(self.years) == 1 else f"{self.years[0]}–{self.years[-1]}"
            self.progress.emit(idx - 1, total, f"Загрузка ИНН {inn}, период {period}…")
            try:
                rows.extend(client.fetch_company_years(inn, self.years))
            except Exception as exc:
                rows.extend(CompanyFinancials.error_row(inn, year, str(exc)) for year in self.years)
            self.progress.emit(idx, total, f"Обработано {idx} из {total}")
        self.completed.emit(rows)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Company Analyst BI — анализ компаний по ИНН")
        self.resize(1450, 900)
        self.setMinimumSize(1050, 720)
        self.settings = QSettings("OpenAI-Demo", "CompanyAnalyst")
        self.data_dir = app_data_dir()
        self.db = HistoryDB(self.data_dir / "history.sqlite3")
        self.current_rows: list[CompanyFinancials] = []
        self.current_report = ""
        self.current_name = ""
        self.current_year = datetime.now().year - 1
        self.current_years = [self.current_year]
        self.fetch_thread: FetchThread | None = None
        self.child_windows: list[QWidget] = []

        QApplication.instance().setStyleSheet(APP_STYLE)
        self._build_ui()
        self.refresh_history()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(18, 0, 18, 0)
        brand = QLabel("COMPANY ANALYST BI")
        brand.setStyleSheet("color:white;font-weight:900;font-size:15px;padding-right:24px;")
        top_layout.addWidget(brand)
        self.nav_buttons = []
        for i, text in enumerate(["Главная", "История", "Настройки"]):
            btn = QPushButton(text)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, index=i: self.show_page(index))
            self.nav_buttons.append(btn)
            top_layout.addWidget(btn)
        top_layout.addStretch()
        root_layout.addWidget(top)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._home_page())
        self.stack.addWidget(self._history_page())
        self.stack.addWidget(self._settings_page())
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.show_page(0)

    def show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.refresh_history()

    def _home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        title = QLabel("Анализ компании по ИНН")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Введите ИНН через «/», выберите конечный год и глубину периода. Приложение загрузит динамику и сохранит её в истории.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_frame = QFrame()
        form_frame.setStyleSheet("QFrame{background:white;border:1px solid #dfe4ef;border-radius:10px;}")
        form = QFormLayout(form_frame)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        self.inn_edit = QLineEdit()
        self.inn_edit.setPlaceholderText("Например: 7707083893/7736050003/7702070139")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Банки 2025 — сравнение")
        self.year_combo = QComboBox()
        current = datetime.now().year
        for y in range(current, 2018, -1):
            self.year_combo.addItem(str(y), y)
        idx = self.year_combo.findData(current - 1)
        if idx >= 0:
            self.year_combo.setCurrentIndex(idx)
        self.period_combo = QComboBox()
        self.period_combo.setToolTip("Выберите количество лет: 1 — только выбранный год; 3–5 — динамика для линейных графиков")
        saved_period = int(self.settings.value("period_years", 5))
        self.year_combo.currentIndexChanged.connect(self._sync_period_options)
        self._sync_period_options(preferred=saved_period)
        self.period_combo.currentIndexChanged.connect(
            lambda _index: self.settings.setValue("period_years", self.selected_period_depth())
        )
        form.addRow("ИНН:", self.inn_edit)
        form.addRow("Название файла / анализа:", self.name_edit)
        form.addRow("Отчётный год:", self.year_combo)
        form.addRow("Глубина периода:", self.period_combo)
        layout.addWidget(form_frame)

        actions = QHBoxLayout()
        self.execute_btn = QPushButton("Выполнить")
        self.execute_btn.setObjectName("primary")
        self.execute_btn.clicked.connect(self.execute_analysis)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.clear_home)
        self.report_btn = QPushButton("Посмотреть отчёт")
        self.report_btn.clicked.connect(self.open_report)
        self.chart_btn = QPushButton("Открыть BI-дашборд")
        self.chart_btn.clicked.connect(self.open_dashboard)
        self.export_btn = QPushButton("Экспорт CSV")
        self.export_btn.clicked.connect(self.export_csv)
        actions.addWidget(self.execute_btn)
        actions.addWidget(clear_btn)
        actions.addStretch()
        actions.addWidget(self.export_btn)
        actions.addWidget(self.report_btn)
        actions.addWidget(self.chart_btn)
        layout.addLayout(actions)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("subtitle")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in TABLE_COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self.open_source_from_cell)
        layout.addWidget(self.table, 1)
        self._set_result_actions_enabled(False)
        return page

    def _history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        title = QLabel("История")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Поиск по названию анализа или ИНН. Двойной клик открывает сохранённый результат.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        row = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Поиск по названию или ИНН…")
        self.history_search.textChanged.connect(self.refresh_history)
        open_btn = QPushButton("Открыть")
        delete_btn = QPushButton("Удалить")
        rerun_btn = QPushButton("Повторить запрос")
        open_btn.clicked.connect(self.open_selected_history)
        delete_btn.clicked.connect(self.delete_selected_history)
        rerun_btn.clicked.connect(self.rerun_selected_history)
        row.addWidget(self.history_search, 1)
        row.addWidget(open_btn)
        row.addWidget(rerun_btn)
        row.addWidget(delete_btn)
        layout.addLayout(row)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["ID", "Название", "Период", "ИНН", "Создано"])
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.doubleClicked.connect(lambda _index: self.open_selected_history())
        layout.addWidget(self.history_table, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 22, 24, 24)
        title = QLabel("Настройки")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        card = QFrame()
        card.setStyleSheet("QFrame{background:white;border:1px solid #dfe4ef;border-radius:10px;}")
        form = QFormLayout(card)
        form.setContentsMargins(18, 18, 18, 18)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(int(self.settings.value("timeout", 25)))
        self.timeout_spin.valueChanged.connect(lambda v: self.settings.setValue("timeout", v))
        source = QLineEdit("https://bo.nalog.gov.ru")
        source.setReadOnly(True)
        data_path = QLineEdit(str(self.data_dir))
        data_path.setReadOnly(True)
        form.addRow("Таймаут запроса, сек.:", self.timeout_spin)
        form.addRow("Источник БФО:", source)
        form.addRow("Локальные данные:", data_path)
        layout.addWidget(card)
        buttons = QHBoxLayout()
        open_data = QPushButton("Открыть папку данных")
        open_site = QPushButton("Открыть сайт ФНС")
        open_data.clicked.connect(self.open_data_folder)
        open_site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://bo.nalog.gov.ru")))
        buttons.addWidget(open_data)
        buttons.addWidget(open_site)
        buttons.addStretch()
        layout.addLayout(buttons)
        info = QLabel(
            "Приложение использует публичный JSON-backend веб-витрины ГИР БО для точечного поиска организаций. "
            "Он не является гарантированным официальным публичным API и может измениться. Все сетевые вызовы вынесены в company_analyst/fns_source.py."
        )
        info.setWordWrap(True)
        info.setObjectName("subtitle")
        layout.addWidget(info)
        layout.addStretch()
        return page

    def _set_result_actions_enabled(self, enabled: bool):
        self.report_btn.setEnabled(enabled)
        self.chart_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    @staticmethod
    def parse_inns(raw: str) -> list[str]:
        parts = re.split(r"[/,;\s]+", raw.strip())
        result = []
        for p in parts:
            digits = re.sub(r"\D", "", p)
            if digits and digits not in result:
                result.append(digits)
        return result

    @staticmethod
    def period_depth_label(years: int) -> str:
        if years == 1:
            return "1 год"
        if 2 <= years <= 4:
            return f"{years} года"
        return f"{years} лет"

    def selected_period_depth(self) -> int:
        if not hasattr(self, "period_combo"):
            return 1
        return int(self.period_combo.currentData() or 1)

    def _sync_period_options(self, _index: int | None = None, preferred: int | None = None) -> None:
        if not hasattr(self, "period_combo"):
            return
        year = int(self.year_combo.currentData())
        max_depth = max(1, min(7, year - 2019 + 1))
        requested = preferred if preferred is not None else self.selected_period_depth()
        requested = max(1, min(int(requested), max_depth))

        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for depth in range(1, max_depth + 1):
            self.period_combo.addItem(self.period_depth_label(depth), depth)
        selected_index = self.period_combo.findData(requested)
        self.period_combo.setCurrentIndex(max(0, selected_index))
        self.period_combo.blockSignals(False)

    def period_label(self) -> str:
        if not self.current_years:
            return str(self.current_year)
        return str(self.current_years[0]) if len(self.current_years) == 1 else f"{self.current_years[0]}–{self.current_years[-1]}"

    def execute_analysis(self):
        inns = self.parse_inns(self.inn_edit.text())
        name = self.name_edit.text().strip()
        year = int(self.year_combo.currentData())
        depth = self.selected_period_depth()
        years = list(range(max(2019, year - depth + 1), year + 1))
        if not inns:
            QMessageBox.warning(self, "Нет ИНН", "Введите хотя бы один ИНН. Для нескольких используйте формат ИНН1/ИНН2/ИННx.")
            return
        invalid = [x for x in inns if len(x) not in (10, 12)]
        if invalid:
            QMessageBox.warning(self, "Некорректный ИНН", f"Проверьте длину ИНН: {', '.join(invalid)}")
            return
        if not name:
            QMessageBox.warning(self, "Нет названия", "Введите название анализа — по нему запись будет находиться в истории.")
            return
        if self.fetch_thread and self.fetch_thread.isRunning():
            return

        self.current_name = name
        self.current_year = year
        self.current_years = years
        self.current_rows = []
        self.current_report = ""
        self.table.setRowCount(0)
        self.execute_btn.setEnabled(False)
        self._set_result_actions_enabled(False)
        self.progress.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress.setRange(0, len(inns))
        self.progress.setValue(0)
        self.progress_label.setText("Подготовка запроса…")

        self.fetch_thread = FetchThread(inns, years, self.timeout_spin.value())
        self.fetch_thread.progress.connect(self.on_fetch_progress)
        self.fetch_thread.completed.connect(self.on_fetch_completed)
        self.fetch_thread.start()

    def on_fetch_progress(self, done: int, total: int, text: str):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_label.setText(text)

    def on_fetch_completed(self, rows):
        self.current_rows = sorted(rows, key=lambda row: (row.inn, -row.year))
        self.current_report = build_report(self.current_rows, self.current_name, self.current_year)
        self.populate_table(self.current_rows)
        self.db.save(self.current_name, self.current_year, self.current_rows, self.current_report)
        self.execute_btn.setEnabled(True)
        self._set_result_actions_enabled(bool(self.current_rows))
        self.progress.setVisible(False)
        self.progress_label.setVisible(False)
        self.refresh_history()
        errors = [r for r in self.current_rows if r.error]
        if errors:
            QMessageBox.information(
                self,
                "Анализ завершён",
                f"Период {self.period_label()}. Строк с данными: {len(self.current_rows)-len(errors)}. "
                f"Недоступных периодов: {len(errors)}. Подробности видны в таблице и отчёте.",
            )
        else:
            companies = len({row.inn for row in self.current_rows})
            QMessageBox.information(
                self,
                "Анализ завершён",
                f"Загружен период {self.period_label()} для {companies} компаний. Данные сохранены в истории.",
            )

    def populate_table(self, rows: list[CompanyFinancials]):
        self.table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, (_, attr) in enumerate(TABLE_COLUMNS):
                value = getattr(row, attr)
                if row.error and attr == "status":
                    value = f"Ошибка: {row.error}"
                item = QTableWidgetItem(format_table_value(attr, value))
                if attr in {"revenue", "cost_sales", "net_profit", "loss", "total_expenses", "assets", "equity", "shortterm_liabilities", "longterm_liabilities", "net_margin", "roa", "roe", "current_ratio", "debt_to_equity"}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if attr == "source_url" and value:
                    item.setToolTip("Двойной клик — открыть источник ФНС")
                if row.error:
                    item.setToolTip(row.error)
                self.table.setItem(r_idx, c_idx, item)
        self.table.resizeRowsToContents()

    def open_source_from_cell(self, row: int, column: int):
        if column != len(TABLE_COLUMNS) - 1 or row >= len(self.current_rows):
            return
        url = self.current_rows[row].source_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def clear_home(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            QMessageBox.information(self, "Идёт загрузка", "Дождитесь завершения текущего запроса.")
            return
        self.inn_edit.clear()
        self.name_edit.clear()
        self.current_rows = []
        self.current_report = ""
        self.table.setRowCount(0)
        self._set_result_actions_enabled(False)

    def open_report(self):
        if not self.current_rows:
            return
        win = ReportWindow(self.current_report, self.current_name, self.period_label(), self)
        win.show()
        self.child_windows.append(win)

    def open_dashboard(self):
        if not self.current_rows:
            return
        try:
            win = DashboardWindow(self.current_rows, self.current_name, self.current_year, self)
            win.show()
            self.child_windows.append(win)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Не удалось открыть BI-дашборд",
                f"Основное приложение продолжит работу.\n\n{exc}",
            )

    def export_csv(self):
        if not self.current_rows:
            return
        default = str(Path.home() / f"{self.current_name}_{self.period_label()}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт CSV", default, "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([c[0] for c in TABLE_COLUMNS] + ["Ошибка"])
                for row in self.current_rows:
                    writer.writerow([format_table_value(attr, getattr(row, attr)) for _, attr in TABLE_COLUMNS] + [row.error])
            QMessageBox.information(self, "Готово", f"CSV сохранён:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))

    def refresh_history(self):
        if not hasattr(self, "history_table"):
            return
        query = self.history_search.text() if hasattr(self, "history_search") else ""
        entries = self.db.list(query)
        self.history_table.setRowCount(len(entries))
        for i, entry in enumerate(entries):
            start = int(entry.get("period_start") or entry["year"])
            end = int(entry.get("period_end") or entry["year"])
            period = str(end) if start == end else f"{start}–{end}"
            values = [entry["id"], entry["name"], period, entry["inns"], entry["created_at"].replace("T", " ")]
            for j, value in enumerate(values):
                self.history_table.setItem(i, j, QTableWidgetItem(str(value)))
        self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def selected_history_id(self) -> int | None:
        row = self.history_table.currentRow()
        if row < 0:
            return None
        item = self.history_table.item(row, 0)
        return int(item.text()) if item else None

    def open_selected_history(self):
        analysis_id = self.selected_history_id()
        if analysis_id is None:
            QMessageBox.information(self, "История", "Выберите запись.")
            return
        data = self.db.get(analysis_id)
        if not data:
            return
        self.current_name = data["name"]
        self.current_year = int(data["year"])
        period_start = int(data.get("period_start") or self.current_year)
        period_end = int(data.get("period_end") or self.current_year)
        self.current_years = list(range(period_start, period_end + 1))
        self.current_rows = data["rows"]
        self.current_report = data["report_text"]
        self.name_edit.setText(self.current_name)
        self.inn_edit.setText(data["inns"])
        idx = self.year_combo.findData(self.current_year)
        if idx >= 0:
            self.year_combo.setCurrentIndex(idx)
        self._sync_period_options(preferred=len(self.current_years))
        self.populate_table(self.current_rows)
        self._set_result_actions_enabled(True)
        self.show_page(0)

    def delete_selected_history(self):
        analysis_id = self.selected_history_id()
        if analysis_id is None:
            QMessageBox.information(self, "История", "Выберите запись.")
            return
        if QMessageBox.question(self, "Удалить", "Удалить выбранный анализ из истории?") == QMessageBox.Yes:
            self.db.delete(analysis_id)
            self.refresh_history()

    def rerun_selected_history(self):
        analysis_id = self.selected_history_id()
        if analysis_id is None:
            QMessageBox.information(self, "История", "Выберите запись.")
            return
        data = self.db.get(analysis_id)
        if not data:
            return
        self.inn_edit.setText(data["inns"])
        self.name_edit.setText(data["name"])
        idx = self.year_combo.findData(int(data["year"]))
        if idx >= 0:
            self.year_combo.setCurrentIndex(idx)
        period_start = int(data.get("period_start") or data["year"])
        period_end = int(data.get("period_end") or data["year"])
        self._sync_period_options(preferred=period_end - period_start + 1)
        self.show_page(0)
        self.execute_analysis()

    def open_data_folder(self):
        path = str(self.data_dir)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть папку:\n{exc}")
