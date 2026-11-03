"""Look up a school on CBSE SARAS by its affiliation number, to pre-fill the registration chat.

SARAS has no API: its public school page is a two-column table of <b>label</b> | value rows.
The result is only a suggestion; the user checks and edits it before anything is saved.
"""
from __future__ import annotations

import logging
import re
import string
from html.parser import HTMLParser

import httpx

log = logging.getLogger(__name__)

SARAS_URL = "https://saras.cbse.gov.in/SARAS/AffiliatedList/AfflicationDetails/{number}"
NUMBER = re.compile(r"\d{4,10}")


class LookupFailed(Exception):
    """SARAS could not be reached or answered with an error."""


class _Rows(HTMLParser):
    """Collects the text of each table row's cells: [[label, value], ...]."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _label(text: str) -> str:
    return re.sub(r"[^a-z]+", " ", text.lower()).strip()


def _tidy(value: str) -> str:
    """SARAS writes most values in capitals; show them as names are usually written."""
    value = value.strip(" ,")
    return string.capwords(value) if value.isupper() else value


def parse(html: str) -> dict | None:
    """The school's details from a SARAS page, or None when the page names no school."""
    p = _Rows()
    p.feed(html)
    found = {_label(r[0]): r[1] for r in p.rows if len(r) >= 2 and r[0]}

    def get(*names: str) -> str:
        return next((found[n] for n in names if found.get(n)), "")

    name = get("name of institution")
    if not name:
        return None
    pin = re.sub(r"\D", "", get("pin code"))
    address = get("postal address")
    if pin:  # the PIN is a field of its own; drop a copy at the end of the address
        address = re.sub(rf"[\s,\-]*{pin}\s*$", "", address)
    period = re.findall(r"\d{2}/\d{2}/\d{4}", get("affiliation period"))
    return {
        "affiliation_number": get("affiliation number"),
        "school_name": _tidy(name),
        "address": _tidy(address),
        "district": _tidy(get("district")),
        "state": _tidy(get("state")),
        "postcode": pin,
        "principal_name": get("name of principal head of institution"),
        "school_level": get("status of the school"),
        "affiliation_to": period[1] if len(period) > 1 else "",
    }


def lookup(number: str) -> dict | None:
    """The school with this affiliation number, None if SARAS has none; LookupFailed if SARAS is unreachable."""
    number = number.strip()
    if not NUMBER.fullmatch(number):
        return None
    try:
        r = httpx.get(SARAS_URL.format(number=number), timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (EvalAI school registration)"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("SARAS lookup for %s failed: %s", number, e)
        raise LookupFailed(str(e)) from e
    return parse(r.text)

SARAS_REPORT_URL = "https://saras.cbse.gov.in/saras/AffiliatedList/ListOfSchdirReport"


def search_by_name(keyword: str) -> list[dict]:
    """Search CBSE SARAS directory by school name/keyword and return matching schools."""
    keyword = keyword.strip()
    if len(keyword) < 2:
        return []
    try:
        r = httpx.get(
            SARAS_REPORT_URL,
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (EvalAI school registration)"},
        )
        if r.status_code != 200:
            return []
        token_match = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', r.text)
        if not token_match:
            return []
        token = token_match.group(1)

        data = {
            "MainRadioValue": "Keyword_wise",
            "InstName_orAddress": keyword,
            "__RequestVerificationToken": token,
        }
        resp = httpx.post(
            SARAS_REPORT_URL,
            data=data,
            timeout=15,
            follow_redirects=True,
            cookies=r.cookies,
            headers={"User-Agent": "Mozilla/5.0 (EvalAI school registration)"},
        )
        if resp.status_code != 200:
            return []

        rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', resp.text, re.DOTALL | re.IGNORECASE)
        results = []
        for row in rows:
            cells = [
                re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', c)).strip()
                for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            ]
            if len(cells) < 6:
                continue

            aff_match = re.search(r'Aff\.\s*No\.\s*:\s*(\d+)', cells[1])
            aff_no = aff_match.group(1) if aff_match else ""

            state_match = re.search(r'State\s*:\s*([^D]+?)(?:District|$)', cells[2])
            dist_match = re.search(r'District\s*:\s*(.+)', cells[2])
            state = _tidy(state_match.group(1).strip()) if state_match else ""
            district = _tidy(dist_match.group(1).strip()) if dist_match else ""

            name_match = re.search(r'Name\s*:\s*([^H]+?)(?:Head/Principal Name:|$)', cells[4])
            princ_match = re.search(r'Head/Principal Name:\s*(.+)', cells[4])
            school_name = _tidy(name_match.group(1).strip()) if name_match else ""
            principal = _tidy(princ_match.group(1).strip()) if princ_match else ""

            addr_match = re.search(r'Address\s*:\s*([^W]+?)(?:Website|$)', cells[5])
            raw_addr = addr_match.group(1).strip() if addr_match else cells[5]
            pin_match = re.search(r'\b\d{6}\b', raw_addr)
            postcode = pin_match.group(0) if pin_match else ""
            address = _tidy(raw_addr)

            if aff_no:
                results.append({
                    "affiliation_number": aff_no,
                    "school_name": school_name or keyword,
                    "address": address,
                    "district": district,
                    "state": state,
                    "postcode": postcode,
                    "principal_name": principal,
                })
                if len(results) >= 8:
                    break
        return results
    except Exception as e:
        log.warning("SARAS search by keyword %s failed: %s", keyword, e)
        return []

