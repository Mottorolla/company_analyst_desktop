from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt


class ReportWindow(QWidget):
    def __init__(self, report_text: str, analysis_name: str, period: int | str, parent=None):
        super().__init__(parent, Qt.Window)
        self.report_text = report_text
        self.analysis_name = analysis_name
        self.period = str(period)
        self.setWindowTitle(f"Отчёт — {analysis_name}")
        self.resize(950, 760)
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        label = QLabel(f"Аналитический отчёт · {analysis_name} · {self.period}")
        label.setObjectName("reportTitle")
        save_btn = QPushButton("Сохранить отчёт TXT")
        copy_btn = QPushButton("Копировать")
        save_btn.clicked.connect(self.save_txt)
        copy_btn.clicked.connect(self.copy_text)
        header.addWidget(label)
        header.addStretch()
        header.addWidget(copy_btn)
        header.addWidget(save_btn)
        root.addLayout(header)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(report_text)
        root.addWidget(self.text, 1)

    def copy_text(self) -> None:
        QApplication.clipboard().setText(self.report_text)

    def save_txt(self) -> None:
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in self.analysis_name).strip() or "report"
        default = str(Path.home() / f"{safe_name}_{self.period}_report.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт", default, "Text file (*.txt)")
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"
        try:
            Path(path).write_text(self.report_text, encoding="utf-8")
            QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить отчёт:\n{exc}")
