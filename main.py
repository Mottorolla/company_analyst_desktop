from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from company_analyst.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Company Analyst BI")
    app.setOrganizationName("Local")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
