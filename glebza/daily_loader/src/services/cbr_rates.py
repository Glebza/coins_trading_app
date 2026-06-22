"""Bank of Russia RUONIA loader."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree

_URL = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
_SOAP_ACTION = "http://web.cbr.ru/RuoniaXML"


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class CbrRatesService:
    def fetch_ruonia(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        start = _utc(start_dt)
        end = _utc(end_dt)
        if end <= start:
            raise ValueError("end_dt must be after start_dt")

        payload = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <RuoniaXML xmlns="http://web.cbr.ru/">
      <fromDate>{start.date().isoformat()}T00:00:00</fromDate>
      <ToDate>{end.date().isoformat()}T00:00:00</ToDate>
    </RuoniaXML>
  </soap:Body>
</soap:Envelope>"""
        request = Request(
            _URL,
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": _SOAP_ACTION,
            },
        )
        with urlopen(request, timeout=30) as response:
            xml_text = response.read().decode("utf-8")
        return self._parse_xml(xml_text)

    def _parse_xml(self, xml_text: str) -> list[dict]:
        root = ElementTree.fromstring(xml_text)
        rows: list[dict] = []
        for element in root.iter():
            children = {_local_name(child.tag): (child.text or "").strip() for child in list(element)}
            lower = {name.lower(): value for name, value in children.items()}
            rate_date = children.get("D0")
            ruonia = lower.get("ruo")
            if not rate_date or not ruonia:
                continue
            rows.append(
                {
                    "rate_code": "RUONIA",
                    "rate_date": date.fromisoformat(rate_date[:10]),
                    "annual_rate": Decimal(ruonia.replace(",", ".")) / Decimal("100"),
                    "source": "cbr",
                    "status": lower.get("status") or None,
                    "published_at": self._parse_datetime(
                        lower.get("published_at")
                        or lower.get("date_publication")
                        or lower.get("pub_date")
                    ),
                }
            )
        rows.sort(key=lambda row: row["rate_date"])
        return rows

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value[:19])
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
