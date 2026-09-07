from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CALENDAR_FILE = Path("data/turnieje.json")
CACHE_FILE = Path("data/szczegoly_turniejow.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
    )
}
VOIVODESHIPS = {
    "dolnośląskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "łódzkie",
    "małopolskie", "mazowieckie", "opolskie", "podkarpackie", "podlaskie",
    "pomorskie", "śląskie", "świętokrzyskie", "warmińsko-mazurskie",
    "wielkopolskie", "zachodniopomorskie",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def text_lines(text: str) -> list[str]:
    return [clean(x) for x in (text or "").splitlines() if clean(x)]


def soup_lines(soup: BeautifulSoup) -> list[str]:
    return text_lines(soup.get_text("\n", strip=True))


def value_after(lines: list[str], labels: list[str]) -> str:
    wanted = [x.casefold().rstrip(":") for x in labels]
    for i, line in enumerate(lines):
        folded = line.casefold().rstrip(":")
        for label in wanted:
            if folded == label:
                if i + 1 < len(lines):
                    return clean(lines[i + 1])
            prefix = label + ":"
            if line.casefold().startswith(prefix):
                value = clean(line[len(prefix):])
                if value:
                    return value
    return ""


def block_after(lines: list[str], labels: list[str], stop_labels: list[str], max_lines: int = 14) -> str:
    wanted = {x.casefold().rstrip(":") for x in labels}
    stops = {x.casefold().rstrip(":") for x in stop_labels}
    start = None
    for i, line in enumerate(lines):
        if line.casefold().rstrip(":") in wanted:
            start = i + 1
            break
    if start is None:
        return ""
    out: list[str] = []
    for line in lines[start:start + max_lines]:
        if line.casefold().rstrip(":") in stops:
            break
        out.append(line)
    return clean(" | ".join(out))


def normalize_voivodeship(value: str) -> str:
    folded = clean(value).casefold()
    folded = folded.replace("województwo", "").replace("wojewodztwo", "").strip(" :-")
    for woj in VOIVODESHIPS:
        if woj in folded:
            return woj
    return folded if folded in VOIVODESHIPS else ""


def pzt_detail_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.replace("TournamentResults.aspx", "Tournament.aspx")
    return urlunparse(("https", parsed.netloc or "portal.pzt.pl", path, "", parsed.query, ""))


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def extract_cuply(session: requests.Session, item: dict) -> dict:
    soup = get_soup(session, item["url"])
    lines = soup_lines(soup)
    raw = "\n".join(lines)
    details = {
        "wpisowe": value_after(lines, ["Wpisowe"]),
        "system_gier": value_after(lines, ["System gier"]),
        "limit_uczestnikow": value_after(lines, ["Limit uczestników"]),
        "typ_gry": value_after(lines, ["Typ gry"]),
        "poziom": value_after(lines, ["Poziom"]),
        "plec": value_after(lines, ["Płeć uczestników"]),
        "organizator": value_after(lines, ["Organizator"]),
        "telefon_organizatora": value_after(lines, ["Numer do organizatora"]),
        "wyzywienie": value_after(lines, ["Wyżywienie"]),
        "zapisy_url": item["url"],
        "szczegoly_url": item["url"],
    }
    m = re.search(r"Miejsce:\s*(.+?)(?:\n|$)", raw, re.I)
    if m:
        details["adres"] = clean(m.group(1))
    desc = block_after(
        lines,
        ["Płeć uczestników"],
        ["Dodatkowe informacje", "Nagrody", "Zobacz obiekt na mapie", "Uczestnicy"],
        max_lines=18,
    )
    plec = details.get("plec", "")
    if desc and plec and desc.startswith(plec):
        desc = clean(desc[len(plec):].lstrip(" |"))
    if desc:
        details["opis"] = desc[:2500]
    cycle_match = re.search(r"Turniej wlicza się do\s+([^\n]+)", raw, re.I)
    if cycle_match:
        details["cykl_szczegolowy"] = clean(cycle_match.group(1))
    return {k: v for k, v in details.items() if v}


def extract_pzt(session: requests.Session, item: dict) -> dict:
    detail_url = pzt_detail_url(item["url"])
    soup = get_soup(session, detail_url)
    lines = soup_lines(soup)
    details = {
        "organizator": value_after(lines, ["Organizator"]),
        "adres": value_after(lines, ["Miejsce turnieju"]),
        "kategorie": value_after(lines, ["Kategorie"]),
        "termin_zgloszen": value_after(lines, ["Termin zgłoszeń"]),
        "termin_odwolan": value_after(lines, ["Termin odwołań"]),
        "dyrektor_turnieju": value_after(lines, ["Dyrektor turnieju"]),
        "sedzia_naczelny": value_after(lines, ["Sędzia naczelny"]),
        "pilka": value_after(lines, ["Piłka"]),
        "zapisy_url": detail_url,
        "szczegoly_url": detail_url,
    }
    fee = block_after(
        lines,
        ["Wpisowe"],
        ["Nagrody", "Zakwaterowanie", "Uwagi", "Termin zgłoszeń", "Dyrektor turnieju"],
        max_lines=12,
    )
    if fee:
        details["wpisowe"] = fee[:1800]
    contact = block_after(
        lines,
        ["Miejsce turnieju"],
        ["Kategorie", "Turniej gł.", "Informacje", "Szczegóły", "Uwagi", "Termin zgłoszeń"],
        max_lines=6,
    )
    if contact:
        details["kontakt"] = contact[:800]
    return {k: v for k, v in details.items() if v}


def main_text_from_page(page) -> str:
    for selector in ["main", "[role='main']"]:
        loc = page.locator(selector)
        if loc.count():
            try:
                text = loc.first.inner_text(timeout=3000)
                if len(clean(text)) > 80:
                    return text
            except Exception:
                pass
    return page.locator("body").inner_text()


def registration_url(page, fallback: str) -> str:
    try:
        links = page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({text:(a.innerText||'').replace(/\\s+/g,' ').trim(), href:a.href}))"""
        )
        for link in links:
            text = clean(link.get("text", "")).casefold()
            href = clean(link.get("href", ""))
            if not href:
                continue
            if re.search(r"zapisy|register|signup|rejestr", href, re.I):
                return href
            if any(token in text for token in ["zapisz", "weź udział", "wez udzial", "dołącz", "dolacz"]):
                return href
    except Exception:
        pass
    return fallback


def extract_browser(page, item: dict) -> dict:
    response = page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"HTTP {response.status}")
    page.wait_for_timeout(900)
    text = main_text_from_page(page)
    lines = text_lines(text)
    details = {
        "organizator": value_after(lines, ["Organizator", "Organizator turnieju"]),
        "wojewodztwo": normalize_voivodeship(value_after(lines, ["Województwo", "Wojewodztwo"])),
        "adres": value_after(lines, ["Adres", "Adres obiektu"]),
        "miejsce": value_after(lines, ["Miejsce turnieju", "Obiekt", "Klub", "Miejsce"]),
        "wpisowe": value_after(lines, ["Wpisowe", "Opłata wpisowa"]),
        "termin_zgloszen": value_after(lines, ["Termin zgłoszeń", "Termin zapisów", "Zapisy do", "Zgłoszenia do"]),
        "system_gier": value_after(lines, ["System gier", "System rozgrywek", "Format"]),
        "limit_uczestnikow": value_after(lines, ["Limit uczestników", "Limit zawodników"]),
        "typ_gry": value_after(lines, ["Typ gry", "Rodzaj gry"]),
        "poziom": value_after(lines, ["Poziom"]),
        "plec": value_after(lines, ["Płeć uczestników", "Płeć"]),
        "nawierzchnia": value_after(lines, ["Nawierzchnia"]),
        "kategorie": value_after(lines, ["Kategorie", "Kategoria"]),
        "zapisy_url": registration_url(page, item["url"]),
        "szczegoly_url": item["url"],
    }
    cycle = ""
    for line in lines:
        m = re.search(r"Turniej cyklu\s+(.+)", line, re.I)
        if m:
            cycle = clean(m.group(1))
            break
    if not cycle:
        cycle = value_after(lines, ["Cykl"])
    if cycle:
        details["cykl_szczegolowy"] = cycle

    opis = block_after(
        lines,
        ["Opis", "Informacje", "Informacje o turnieju"],
        ["Uczestnicy", "Nagrody", "Zapisy", "Kontakt", "Organizator", "Miejsce"],
        max_lines=24,
    )
    if opis:
        details["opis"] = opis[:2500]

    if item.get("zrodlo") == "Kluby.org":
        try:
            links = page.locator("a[href]").evaluate_all(
                """els => els.map(a => a.href).filter(Boolean)"""
            )
            signup = next((href for href in links if re.search(r"/turnieje/\d+/zapisy", href)), "")
            if signup:
                details["zapisy_url"] = signup
        except Exception:
            pass

    return {k: v for k, v in details.items() if v}


def parse_last_success(entry: dict) -> date | None:
    value = entry.get("ostatnie_poprawne_pobranie_utc") or ""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return None


def due_for_refresh(item: dict, entry: dict, today: date) -> bool:
    last = parse_last_success(entry)
    if last is None:
        return True
    try:
        start = date.fromisoformat(item.get("data_od", ""))
        end = date.fromisoformat(item.get("data_do") or item.get("data_od", ""))
    except ValueError:
        return (today - last).days >= 7

    if start <= today <= end or (start - today).days <= 7:
        interval = 1
    elif (start - today).days <= 30:
        interval = 3
    else:
        interval = 7
    return (today - last).days >= interval


def merge_details(item: dict, details: dict) -> None:
    if not details:
        return
    item["szczegoly"] = details
    promotable = [
        "organizator", "adres", "wpisowe", "termin_zgloszen", "system_gier",
        "limit_uczestnikow", "nawierzchnia", "zapisy_url", "opis",
        "telefon_organizatora", "kontakt", "cykl_szczegolowy",
        "dyrektor_turnieju", "pilka",
    ]
    for key in promotable:
        if details.get(key):
            item[key] = details[key]
    for key in ["miejsce", "kategorie", "typ_gry", "poziom", "plec"]:
        if details.get(key):
            item[key] = details[key]
    if details.get("wojewodztwo"):
        item["wojewodztwo"] = details["wojewodztwo"]


def main() -> None:
    calendar = load_json(CALENDAR_FILE, {})
    items = calendar.get("turnieje", [])
    if not items:
        raise RuntimeError("Brak turniejów w data/turnieje.json")

    cache_payload = load_json(CACHE_FILE, {"turnieje": {}})
    cache = cache_payload.setdefault("turnieje", {})
    current_ids = {str(item.get("id")) for item in items if item.get("id")}
    now = now_iso()
    today = date.today()

    for event_id, entry in cache.items():
        if event_id not in current_ids:
            if entry.get("aktywny_w_kalendarzu", True):
                entry["usuniety_z_kalendarza_utc"] = now
            entry["aktywny_w_kalendarzu"] = False

    due = []
    for item in items:
        event_id = str(item.get("id"))
        entry = cache.setdefault(event_id, {
            "id": event_id,
            "zrodlo": item.get("zrodlo", ""),
            "url": item.get("url", ""),
            "pierwsze_wykrycie_utc": now,
            "dane": {},
        })
        entry["aktywny_w_kalendarzu"] = True
        entry["ostatnio_widziany_w_kalendarzu_utc"] = now
        entry["nazwa"] = item.get("nazwa", "")
        entry["data_od"] = item.get("data_od", "")
        entry["data_do"] = item.get("data_do", "")
        entry["url"] = item.get("url", "")
        if due_for_refresh(item, entry, today):
            due.append(item)

    print(f"Szczegóły: {len(due)} turniejów wymaga pobrania/odświeżenia z {len(items)} aktywnych")
    session = requests.Session()
    browser_sources = {"PLT", "Kluby.org"}
    browser_due = [item for item in due if item.get("zrodlo") in browser_sources]
    http_due = [item for item in due if item.get("zrodlo") not in browser_sources]

    success = 0
    failed = 0

    for item in http_due:
        event_id = str(item["id"])
        entry = cache[event_id]
        entry["ostatnia_proba_utc"] = now_iso()
        try:
            if item.get("zrodlo") == "Cuply":
                details = extract_cuply(session, item)
            elif item.get("zrodlo") == "PZT TOP":
                details = extract_pzt(session, item)
            else:
                details = {}
            if details:
                entry["dane"] = {**entry.get("dane", {}), **details}
            entry["ostatnie_poprawne_pobranie_utc"] = now_iso()
            entry.pop("ostatni_blad", None)
            success += 1
        except Exception as exc:
            entry["ostatni_blad"] = f"{type(exc).__name__}: {exc}"
            failed += 1
        time.sleep(0.45)

    if browser_due:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="pl-PL", user_agent=HEADERS["User-Agent"])
            page = context.new_page()
            page.set_default_timeout(15000)
            for item in browser_due:
                event_id = str(item["id"])
                entry = cache[event_id]
                entry["ostatnia_proba_utc"] = now_iso()
                try:
                    details = extract_browser(page, item)
                    if details:
                        entry["dane"] = {**entry.get("dane", {}), **details}
                    entry["ostatnie_poprawne_pobranie_utc"] = now_iso()
                    entry.pop("ostatni_blad", None)
                    success += 1
                except Exception as exc:
                    entry["ostatni_blad"] = f"{type(exc).__name__}: {exc}"
                    failed += 1
                page.wait_for_timeout(500)
            browser.close()

    # Jeśli szczegóły źródła PLT nie rozstrzygają niejednoznacznego "Kamienia",
    # nie pokazujemy województwa z wcześniejszego geokodowania/cache jako pewnika.
    for item in items:
        event_id = str(item.get("id"))
        details = cache.get(event_id, {}).get("dane", {})
        merge_details(item, details)
        if clean(item.get("miasto")).casefold() == "kamień" and item.get("zrodlo") == "PLT" and not details.get("wojewodztwo"):
            item["wojewodztwo"] = ""

    cache_payload["aktualizacja_utc"] = now_iso()
    cache_payload["liczba_rekordow"] = len(cache)
    cache_payload["liczba_aktywnych"] = len(items)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    calendar["szczegoly_aktualizacja_utc"] = now_iso()
    calendar["szczegoly_pobrano_w_tym_przebiegu"] = success
    calendar["szczegoly_bledy_w_tym_przebiegu"] = failed
    CALENDAR_FILE.write_text(json.dumps(calendar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Szczegóły: sukces {success}, błędy {failed}, cache {len(cache)} rekordów")


if __name__ == "__main__":
    main()
