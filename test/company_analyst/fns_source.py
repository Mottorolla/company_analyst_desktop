from __future__ import annotations

import html
import re
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import CompanyFinancials, get_current_value


BASE_URL = "https://bo.nalog.gov.ru"
SEARCH_PATH = "/advanced-search/organizations/search"
BFO_PATH = "/nbo/organizations/{organization_id}/bfo/"


class FNSDataError(RuntimeError):
    pass


def _plain(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _status_label(code: str) -> str:
    mapping = {
        "ACTIVE": "Действующая",
        "LIQUIDATED": "Ликвидирована",
        "LIQUIDATING": "В процессе ликвидации",
        "REORGANIZING": "В процессе реорганизации",
    }
    return mapping.get(code, code or "Не указан")


class FNSBFOClient:
    """Client for the public web-backend used by bo.nalog.gov.ru.

    The JSON endpoints are public frontend endpoints, not a guaranteed long-term API.
    All endpoint paths are centralized in this module so they can be replaced easily.
    """

    def __init__(self, timeout: int = 25, min_delay: float = 0.35):
        self.timeout = timeout
        self.min_delay = min_delay
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
                "Referer": f"{BASE_URL}/",
            }
        )
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        try:
            resp = self.session.get(BASE_URL + path, params=params, timeout=self.timeout)
            self._last_request = time.monotonic()
        except requests.RequestException as exc:
            raise FNSDataError(f"Сетевая ошибка ФНС: {exc}") from exc
        if resp.status_code != 200:
            raise FNSDataError(f"ФНС вернула HTTP {resp.status_code} для {path}")
        try:
            return resp.json()
        except ValueError as exc:
            raise FNSDataError("ФНС вернула ответ в неожиданном формате") from exc

    def search_company(self, inn: str) -> dict[str, Any]:
        payload = self._get_json(SEARCH_PATH, {"query": inn, "page": 0, "size": 20})
        content = payload.get("content", []) if isinstance(payload, dict) else []
        if not content:
            raise FNSDataError("Организация не найдена в публичном поиске БФО")

        exact = []
        for item in content:
            if re.sub(r"\D", "", _plain(item.get("inn"))) == inn:
                exact.append(item)
        if exact:
            return exact[0]
        if len(content) == 1:
            return content[0]
        raise FNSDataError("Поиск ФНС вернул несколько организаций, точное совпадение ИНН не найдено")

    def fetch_reports(self, organization_id: int) -> list[dict[str, Any]]:
        payload = self._get_json(BFO_PATH.format(organization_id=organization_id))
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "data", "reports", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        raise FNSDataError("Неожиданная структура списка бухгалтерской отчетности")

    @staticmethod
    def _choose_correction(report: dict[str, Any]) -> dict[str, Any]:
        candidates = []
        for item in report.get("typeCorrections", []) or []:
            corr = (item or {}).get("correction")
            if corr:
                candidates.append(corr)
        if not candidates:
            raise FNSDataError("Для выбранного года нет доступной корректировки БФО")
        return max(candidates, key=lambda c: (c.get("correctionVersion", -1), c.get("id", -1)))

    def _parse_company_year(
        self,
        org: dict[str, Any],
        reports: list[dict[str, Any]],
        inn: str,
        year: int,
    ) -> CompanyFinancials:
        org_id = org.get("id")
        if org_id is None:
            raise FNSDataError("В ответе ФНС отсутствует organizationId")
        report = next((r for r in reports if str(r.get("period")) == str(year)), None)
        if report is None:
            available = sorted({str(r.get("period")) for r in reports if r.get("period")}, reverse=True)
            suffix = f" Доступные годы: {', '.join(available[:8])}." if available else ""
            raise FNSDataError(f"Бухгалтерская отчетность за {year} год не найдена.{suffix}")

        corr = self._choose_correction(report)
        fr = corr.get("financialResult") or {}
        bal = corr.get("balance") or {}

        company = CompanyFinancials(
            name=_plain(org.get("shortName")) or _plain(org.get("fullName")) or f"ИНН {inn}",
            inn=inn,
            ogrn=_plain(org.get("ogrn")),
            year=year,
            region=_plain(org.get("region")),
            okved=_plain(org.get("okved2")),
            status=_status_label(_plain(org.get("statusCode"))),
            organization_id=int(org_id),
            correction_id=corr.get("id"),
            published_date=_plain(report.get("publishedCorrectionDate") or report.get("actualBfoDate")),
            revenue=get_current_value(fr, 2110),
            cost_sales=get_current_value(fr, 2120),
            gross_profit=get_current_value(fr, 2100),
            selling_expenses=get_current_value(fr, 2210),
            admin_expenses=get_current_value(fr, 2220),
            sales_profit=get_current_value(fr, 2200),
            interest_income=get_current_value(fr, 2320),
            interest_expenses=get_current_value(fr, 2330),
            other_income=get_current_value(fr, 2340),
            other_expenses=get_current_value(fr, 2350),
            profit_before_tax=get_current_value(fr, 2300),
            income_tax=get_current_value(fr, 2410) or get_current_value(fr, 2411),
            net_profit=get_current_value(fr, 2400),
            noncurrent_assets=get_current_value(bal, 1100),
            current_assets=get_current_value(bal, 1200),
            equity=get_current_value(bal, 1300),
            longterm_liabilities=get_current_value(bal, 1400),
            shortterm_liabilities=get_current_value(bal, 1500),
            assets=get_current_value(bal, 1600),
            liabilities=get_current_value(bal, 1700),
            cash=get_current_value(bal, 1250),
            receivables=get_current_value(bal, 1230),
            payables=get_current_value(bal, 1520),
        )
        company.source_url = (
            f"{BASE_URL}/download/bfo/pdf/{org_id}?period={year}&detailId={company.correction_id}"
            if company.correction_id
            else f"{BASE_URL}/organizations-card/{org_id}"
        )
        return company

    def fetch_company_years(self, inn: str, years: list[int]) -> list[CompanyFinancials]:
        """Load one company once and parse every requested reporting year."""
        requested = sorted(set(int(year) for year in years))
        if not requested:
            return []
        org = self.search_company(inn)
        org_id = org.get("id")
        if org_id is None:
            raise FNSDataError("В ответе ФНС отсутствует organizationId")
        reports = self.fetch_reports(int(org_id))
        result: list[CompanyFinancials] = []
        for year in requested:
            try:
                result.append(self._parse_company_year(org, reports, inn, year))
            except FNSDataError as exc:
                result.append(CompanyFinancials.error_row(inn, year, str(exc)))
        return result

    def fetch_company_year(self, inn: str, year: int) -> CompanyFinancials:
        row = self.fetch_company_years(inn, [year])[0]
        if row.error:
            raise FNSDataError(row.error)
        return row
