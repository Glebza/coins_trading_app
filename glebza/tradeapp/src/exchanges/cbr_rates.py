"""Bank of Russia market-rate loaders."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree


_CBR_DAILY_INFO_URL = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
_RUONIA_SOAP_ACTION = "http://web.cbr.ru/RuoniaXML"


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_cbr_decimal(value: str) -> Decimal:
    return Decimal(value.strip().replace(",", "."))


def _parse_cbr_date(value: str) -> date:
    # CBR XML date-times are easier to treat by calendar date; avoid timezone shifts.
    return date.fromisoformat(value.strip()[:10])


class CbrRatesService:
    """Fetch public funding-rate data from the Bank of Russia."""

    def fetch_ruonia(self, from_dt: datetime, to_dt: datetime) -> list[dict]:
        """Fetch RUONIA rates from CBR and return DB-ready rows.

        ``annual_rate`` is stored as a decimal fraction: 14.07% -> 0.1407.
        """
        from_utc = _normalize_dt(from_dt)
        to_utc = _normalize_dt(to_dt)
        if to_utc <= from_utc:
            raise ValueError("to_dt must be after from_dt")

        payload = self._build_ruonia_xml_request(from_utc, to_utc)
        request = Request(
            _CBR_DAILY_INFO_URL,
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": _RUONIA_SOAP_ACTION,
            },
        )
        with urlopen(request, timeout=30) as response:
            xml_text = response.read().decode("utf-8")
        return self._parse_ruonia_xml(xml_text)

    def _build_ruonia_xml_request(self, from_dt: datetime, to_dt: datetime) -> str:
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RuoniaXML xmlns="http://web.cbr.ru/">
      <fromDate>{from_dt.date().isoformat()}T00:00:00</fromDate>
      <ToDate>{to_dt.date().isoformat()}T00:00:00</ToDate>
    </RuoniaXML>
  </soap:Body>
</soap:Envelope>"""

    def _parse_ruonia_xml(self, xml_text: str) -> list[dict]:
        root = ElementTree.fromstring(xml_text)
        rows: list[dict] = []
        for element in root.iter():
            children = {_local_name(child.tag): (child.text or "").strip() for child in list(element)}
            lower_children = {name.lower(): value for name, value in children.items()}
            rate_date = children.get("D0")
            ruonia = lower_children.get("ruo")
            if not rate_date or not ruonia:
                continue

            rows.append(
                {
                    "rate_code": "RUONIA",
                    "rate_date": _parse_cbr_date(rate_date),
                    "annual_rate": _parse_cbr_decimal(ruonia) / Decimal("100"),
                    "source": "cbr",
                    "status": self._optional_value(lower_children, "status"),
                    "published_at": self._parse_optional_datetime(
                        self._optional_value(lower_children, "published_at")
                        or self._optional_value(lower_children, "date_publication")
                        or self._optional_value(lower_children, "pub_date")
                    ),
                }
            )
        rows.sort(key=lambda row: row["rate_date"])
        return rows

    def _optional_value(self, values: dict[str, str], name: str) -> Optional[str]:
        value = values.get(name)
        return value or None

    def _parse_optional_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value[:19])
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
