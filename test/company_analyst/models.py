from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


def _num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class CompanyFinancials:
    name: str
    inn: str
    ogrn: str = ""
    year: int = 0
    region: str = ""
    okved: str = ""
    status: str = ""
    organization_id: Optional[int] = None
    correction_id: Optional[int] = None
    published_date: str = ""

    revenue: Optional[float] = None
    cost_sales: Optional[float] = None
    gross_profit: Optional[float] = None
    selling_expenses: Optional[float] = None
    admin_expenses: Optional[float] = None
    sales_profit: Optional[float] = None
    interest_income: Optional[float] = None
    interest_expenses: Optional[float] = None
    other_income: Optional[float] = None
    other_expenses: Optional[float] = None
    profit_before_tax: Optional[float] = None
    income_tax: Optional[float] = None
    net_profit: Optional[float] = None

    noncurrent_assets: Optional[float] = None
    current_assets: Optional[float] = None
    equity: Optional[float] = None
    longterm_liabilities: Optional[float] = None
    shortterm_liabilities: Optional[float] = None
    assets: Optional[float] = None
    liabilities: Optional[float] = None
    cash: Optional[float] = None
    receivables: Optional[float] = None
    payables: Optional[float] = None

    source_url: str = ""
    error: str = ""

    @property
    def loss(self) -> Optional[float]:
        if self.net_profit is None:
            return None
        return abs(self.net_profit) if self.net_profit < 0 else 0.0

    @property
    def total_expenses(self) -> Optional[float]:
        vals = [
            self.cost_sales,
            self.selling_expenses,
            self.admin_expenses,
            self.interest_expenses,
            self.other_expenses,
        ]
        present = [abs(v) for v in vals if v is not None]
        return sum(present) if present else None

    @property
    def net_margin(self) -> Optional[float]:
        if not self.revenue or self.net_profit is None:
            return None
        return self.net_profit / self.revenue * 100.0

    @property
    def roa(self) -> Optional[float]:
        if not self.assets or self.net_profit is None:
            return None
        return self.net_profit / self.assets * 100.0

    @property
    def roe(self) -> Optional[float]:
        if not self.equity or self.net_profit is None:
            return None
        return self.net_profit / self.equity * 100.0

    @property
    def current_ratio(self) -> Optional[float]:
        if not self.shortterm_liabilities or self.current_assets is None:
            return None
        return self.current_assets / self.shortterm_liabilities

    @property
    def debt_to_equity(self) -> Optional[float]:
        if not self.equity:
            return None
        debt = sum(v for v in [self.longterm_liabilities, self.shortterm_liabilities] if v is not None)
        return debt / self.equity

    @property
    def asset_turnover(self) -> Optional[float]:
        if not self.assets or self.revenue is None:
            return None
        return self.revenue / self.assets

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyFinancials":
        fields = cls.__dataclass_fields__.keys()
        cleaned = {k: data.get(k) for k in fields if k in data}
        return cls(**cleaned)

    @classmethod
    def error_row(cls, inn: str, year: int, message: str) -> "CompanyFinancials":
        return cls(name="Нет данных", inn=inn, year=year, status="Ошибка", error=message)


def get_current_value(obj: dict[str, Any], code: int) -> Optional[float]:
    return _num(obj.get(f"current{code}"))
