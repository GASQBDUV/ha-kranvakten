"""Klient för EDP Future Webb (FutureWebBasic), t.ex. Lerums kommuns VA-portal.

Flöde (ingen CSRF-token behövs):
  1. GET  /EDPLogin/LogIn                    -> sessionscookie
  2. POST /EDPLogin/Authenticate             CustomerId, Identitynumber
  3. GET  /MyServices/SelectBuilding         -> lista anläggningar (SelectedBuildingID)
  4. POST /MyServices/ShowMyServices         SelectedBuildingID=<id>
       -> HTML med första abonnemanget + lista över abonnemang (SelectedServiceID)
  5. POST /MyServices/ShowMyServices         SelectedServiceID=<id>  (för övriga abonnemang)
  6. GET  /Login/LogOut
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import aiohttp

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
TIMEOUT = aiohttp.ClientTimeout(total=60)


class EdpError(Exception):
    """Allmänt fel mot portalen."""


class EdpAuthError(EdpError):
    """Fel kundnummer/personnummer."""


@dataclass
class Service:
    """Ett abonnemang (t.ex. vatten med mätare)."""

    service_id: str
    building_id: str
    building_name: str
    description: str | None = None
    meter_number: str | None = None
    last_reading_date: date | None = None
    last_reading: float | None = None
    annual_consumption: float | None = None
    estimated_annual_cost: float | None = None


@dataclass
class EdpData:
    """Allt som hämtats vid en uppdatering."""

    services: dict[str, Service] = field(default_factory=dict)


# ---------------------------------------------------------------- parsing ---

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _text(raw_html: str) -> str:
    """HTML -> en rad text med enkla mellanslag."""
    no_tags = _TAG_RE.sub(" ", raw_html)
    return _WS_RE.sub(" ", html.unescape(no_tags)).strip()


def parse_number(value: str | None) -> float | None:
    """'7.520,32 kr' -> 7520.32, '28,0 m³' -> 28.0."""
    if not value:
        return None
    match = re.search(r"-?[\d.\s ]*\d(?:,\d+)?", value)
    if not match:
        return None
    num = match.group(0).replace(" ", "").replace(" ", "").replace(".", "")
    try:
        return float(num.replace(",", "."))
    except ValueError:
        return None


def parse_options(raw_html: str, select_name: str) -> list[tuple[str, str]]:
    """Plocka ut (value, text) för alla <option> i en <select name=...>."""
    sel = re.search(
        rf'<select[^>]*name="{re.escape(select_name)}"[^>]*>(.*?)</select>',
        raw_html,
        re.S | re.I,
    )
    if not sel:
        return []
    return [
        (value, _text(text))
        for value, text in re.findall(
            r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', sel.group(1), re.S | re.I
        )
        if value
    ]


def _field(text: str, label: str, pattern: str) -> str | None:
    match = re.search(rf"{label}\s*:?\s*({pattern})", text, re.I)
    return match.group(1).strip() if match else None


def parse_service_page(raw_html: str) -> dict:
    """Läs ut värdena från sidan ShowMyServices."""
    text = _text(raw_html)
    num = r"-?[\d.\s ]*\d(?:,\d+)?"

    selected = re.search(
        r'<option[^>]*selected="selected"[^>]*value="(\d+)"|'
        r'<option[^>]*value="(\d+)"[^>]*selected',
        raw_html,
    )
    reading_date = _field(text, "Senaste avläsningsdatum", r"\d{4}-\d{2}-\d{2}")

    return {
        "service_id": _field(text, "Abonnemangsnummer", r"\d+")
        or (selected and (selected.group(1) or selected.group(2))),
        "meter_number": _field(text, "Mätarnummer", r"[\w-]+"),
        "last_reading_date": date.fromisoformat(reading_date) if reading_date else None,
        "last_reading": parse_number(_field(text, r"Senaste avläsning(?!sdatum)", num)),
        "annual_consumption": parse_number(_field(text, "Aktuell årsförbrukning", num)),
        "estimated_annual_cost": parse_number(_field(text, "Beräknad årskostnad", num)),
    }


def _summary(raw_html: str) -> str:
    """Kort, ofarlig beskrivning av en sida för felsökning (titel + felmeddelanden)."""
    title = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.S | re.I)
    errors = re.findall(
        r'class="[^"]*(?:validation|error|Error|alert)[^"]*"[^>]*>(.*?)</',
        raw_html,
        re.S,
    )
    errors = [e for e in (_text(x) for x in errors) if e]
    has_login_form = 'name="Identitynumber"' in raw_html
    body = re.search(r"<body[^>]*>(.*)", raw_html, re.S | re.I)
    snippet = _text(re.sub(r"<script.*?</script>|<style.*?</style>", " ",
                           body.group(1) if body else raw_html, flags=re.S | re.I))
    return (
        f"titel={_text(title.group(1)) if title else '?'!r}, "
        f"inloggningsformulär={has_login_form}, fel={errors[:5]}, "
        f"längd={len(raw_html)}, text={snippet[:200]!r}"
    )


def _is_logged_in(raw_html: str) -> bool:
    return "LogOut" in raw_html and 'name="Identitynumber"' not in raw_html


# ----------------------------------------------------------------- client ---


class EdpFutureClient:
    """Loggar in och hämtar abonnemangsdata."""

    def __init__(self, base_url: str, customer_id: str, personal_number: str) -> None:
        self._base = base_url.rstrip("/")
        self._customer_id = str(customer_id).strip()
        self._personal_number = re.sub(r"\D", "", str(personal_number))
        self._origin = self._base
        self._session_jar: aiohttp.CookieJar | None = None
        self.last_status: int | None = None
        self.last_url: str | None = None
        self.last_history: list[str] = []

    async def async_fetch(self) -> EdpData:
        """Logga in, hämta alla abonnemang och logga ut."""
        jar = aiohttp.CookieJar(unsafe=True)
        origin = re.match(r"https?://[^/]+", self._base)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
        }
        self._origin = origin.group(0) if origin else self._base
        async with aiohttp.ClientSession(
            cookie_jar=jar, timeout=TIMEOUT, headers=headers
        ) as session:
            self._session_jar = jar
            await self._login(session)
            try:
                return await self._fetch_services(session)
            finally:
                try:
                    async with session.get(f"{self._base}/Login/LogOut"):
                        pass
                except aiohttp.ClientError:
                    pass

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        data=None,
        referer: str | None = None,
    ) -> str:
        url = f"{self._base}{path}"
        headers: dict[str, str] = {}
        if data is not None:
            headers["Origin"] = self._origin
            headers["Referer"] = referer or url
        try:
            async with session.request(method, url, data=data, headers=headers) as resp:
                body = await resp.text()
                self.last_status = resp.status
                self.last_url = str(resp.url)
                self.last_history = [
                    f"{r.status} {r.headers.get('Location', '')}" for r in resp.history
                ]
                _LOGGER.debug(
                    "%s %s -> %s %s (redirects: %s)",
                    method, path, resp.status, resp.url, self.last_history,
                )
                if resp.status >= 400:
                    raise EdpError(
                        f"{method} {path} gav HTTP {resp.status}: {_summary(body)}"
                    )
                return body
        except aiohttp.ClientError as err:
            raise EdpError(f"{method} {path} misslyckades: {err}") from err

    async def _login(self, session: aiohttp.ClientSession) -> None:
        login_url = f"{self._base}/EDPLogin/LogIn"
        await self._request(session, "GET", "/EDPLogin/LogIn")
        cookies_before = sorted(c.key for c in self._session_jar)
        body = await self._request(
            session,
            "POST",
            "/EDPLogin/Authenticate",
            data={
                "CustomerId": self._customer_id,
                "Identitynumber": self._personal_number,
            },
            referer=login_url,
        )
        if not _is_logged_in(body):
            _LOGGER.warning(
                "Inloggning nekad. Status %s, hamnade på %s, redirects %s, "
                "cookies före POST %s, efter %s. Sida: %s",
                self.last_status,
                self.last_url,
                self.last_history,
                cookies_before,
                sorted(c.key for c in self._session_jar),
                _summary(body),
            )
            raise EdpAuthError("Inloggningen misslyckades (kontrollera kund-/personnummer)")

    async def _fetch_services(self, session: aiohttp.ClientSession) -> EdpData:
        data = EdpData()
        select_page = await self._request(session, "GET", "/MyServices/SelectBuilding")
        if not _is_logged_in(select_page):
            raise EdpAuthError("Sessionen avbröts")
        buildings = parse_options(select_page, "SelectedBuildingID")
        if not buildings:
            raise EdpError("Hittade inga anläggningar på kontot")

        for building_id, building_name in buildings:
            page = await self._request(
                session,
                "POST",
                "/MyServices/ShowMyServices",
                data={"SelectedBuildingID": building_id},
            )
            services = parse_options(page, "SelectedServiceID")
            pages: dict[str, str] = {}
            first = parse_service_page(page)
            if first.get("service_id"):
                pages[str(first["service_id"])] = page

            for service_id, _desc in services:
                if service_id in pages:
                    continue
                pages[service_id] = await self._request(
                    session,
                    "POST",
                    "/MyServices/ShowMyServices",
                    data={"SelectedServiceID": service_id},
                )

            descriptions = dict(services)
            for service_id, service_page in pages.items():
                values = parse_service_page(service_page)
                values["service_id"] = service_id
                data.services[service_id] = Service(
                    building_id=building_id,
                    building_name=re.sub(r"^\(\d+\)\s*", "", building_name),
                    description=descriptions.get(service_id),
                    **values,
                )

        _LOGGER.debug("Hämtade %s abonnemang", len(data.services))
        return data
