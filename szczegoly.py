from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CALENDAR_FILE = Path("data/turnieje.json")
CACHE_FILE = Path("data/szczegoly_turniejow.json")
UNRESOLVED_FILE = Path("data/nierozpoznane_lokalizacje.json")
PARSER_VERSION = 2
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
        folded = line.casefold()
        stripped = folded.rstrip(":")
        for label in wanted:
            if stripped == label:
                if i + 1 < len(lines):
                    return clean(lines[i + 1])
            prefix = label + ":"
            if folded.startswith(prefix):
                value = clean(line[len(prefix):])
                if value:
                    return value
    return ""


def value_prefix(lines: list[str], labels: list[str]) -> str:
    wanted = [clean(x).casefold().rstrip(":") for x in labels]
    for line in lines:
        folded = line.casefold()
        for label in wanted:
            for sep in (":", " "):
                prefix = label + sep
                if folded.startswith(prefix):
                    value = clean(line[len(prefix):])
                    if value:
                        return value
    return ""


def normalize_voivodeship(value: str) -> str:
    folded = clean(value).casefold()
    folded = folded.replace("województwo", "").replace("wojewodztwo", "").strip(" :-")
    for woj in VOIVODESHIPS:
        if woj in folded:
            return woj
    return folded if folded in VOIVODESHIPS else ""


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
    cycle_match = re.search(r"Turniej wlicza się do\s+([^\n]+)", raw, re.I)
    if cycle_match:
        details["cykl_szczegolowy"] = clean(cycle_match.group(1))
    return {k: v for k, v in details.items() if v}


def extract_pzt(session: requests.Session, item: dict) -> dict:
    detail_url = re.sub(r"^http://", "https://", item["url"], flags=re.I)
    soup = get_soup(session, detail_url)
    lines = soup_lines(soup)
    page_text = clean(soup.get_text(" ", strip=True))
    if clean(item.get("nazwa")) and clean(item["nazwa"]) not in page_text:
        raise RuntimeError("PZT: strona szczegółów nie zawiera oczekiwanej nazwy turnieju")

    details = {
        "organizator": value_after(lines, ["Organizator"]),
        "adres": value_after(lines, ["Miejsce turnieju"]),
        "kategorie": value_after(lines, ["Kategorie"]),
        "termin_zgloszen": value_after(lines, ["Termin zgłoszeń"]),
        "termin_odwolan": value_after(lines, ["Termin odwołań"]),
        "dyrektor_turnieju": value_after(lines, ["Dyrektor turnieju"]),
        "sedzia_naczelny": value_after(lines, ["Sędzia naczelny"]),
        "pilka": value_after(lines, ["Piłka"]),
        "szczegoly_url": detail_url,
        "zapisy_url": detail_url,
    }

    try:
        idx = next(i for i, line in enumerate(lines) if line.casefold().rstrip(":") == "dyrektor turnieju")
        contact_lines = []
        for line in lines[idx + 2:idx + 6]:
            if line.casefold().rstrip(":") in {"sędzia naczelny", "wpisowe", "rozgrywki"}:
                break
            if line.casefold().startswith(("tel.", "tel:", "email:", "e-mail:")):
                contact_lines.append(line)
        if contact_lines:
            details["kontakt"] = " | ".join(contact_lines)
    except StopIteration:
        pass

    try:
        start = next(i for i, line in enumerate(lines) if line.casefold().rstrip(":") == "wpisowe") + 1
        fee_lines = []
        for line in lines[start:start + 10]:
            if line.casefold().rstrip(":") in {"rozgrywki", "nagrody", "zakwaterowanie", "uwagi"}:
                break
            fee_lines.append(line)
        if fee_lines:
            details["wpisowe"] = " | ".join(fee_lines)
    except StopIteration:
        pass

    try:
        idx = next(i for i, line in enumerate(lines) if line.casefold().rstrip(":") == "typ")
        if idx + 1 < len(lines):
            details["typ_gry"] = lines[idx + 1]
    except StopIteration:
        pass

    uwagi = value_after(lines, ["Uwagi"])
    if uwagi:
        details["opis"] = uwagi[:1800]
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


def links_from_page(page) -> list[dict]:
    try:
        return page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({text:(a.innerText||'').replace(/\\s+/g,' ').trim(), href:a.href}))"""
        )
    except Exception:
        return []


def registration_url(page, fallback: str) -> str:
    links = links_from_page(page)
    # Najpierw CTA konkretnego turnieju. Nie łapiemy ogólnego "Dołącz do gry"
    # z nagłówka PLT przed przyciskiem "WEŹ UDZIAŁ" wydarzenia.
    for link in links:
        text = clean(link.get("text", "")).casefold()
        href = clean(link.get("href", ""))
        if href and any(token in text for token in ["weź udział", "wez udzial", "zapisz się", "zapisz sie", "zapisz się online", "zapisz sie online"]):
            return href
    for link in links:
        href = clean(link.get("href", ""))
        if href and re.search(r"/turnieje/\d+/zapisy|register|signup|rejestr", href, re.I):
            return href
    return fallback


def extract_plt(page, item: dict) -> dict:
    response = page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"HTTP {response.status}")
    page.wait_for_timeout(900)
    lines = text_lines(main_text_from_page(page))

    miejsce_line = value_prefix(lines, ["Miejsce"])
    woj = normalize_voivodeship(miejsce_line.split(",")[-1]) if "," in miejsce_line else ""

    venue_full = ""
    for i, line in enumerate(lines):
        if line.casefold().startswith("nawierzchnia latem:") and i > 0:
            venue_full = lines[i - 1]
            break
    venue_name = venue_full.split(",", 1)[0].strip() if venue_full else ""

    cycle = ""
    for line in lines:
        m = re.search(r"Turniej cyklu\s+(.+)", line, re.I)
        if m:
            cycle = clean(m.group(1))
            break

    details = {
        "cykl_szczegolowy": cycle,
        "miejsce": venue_name or venue_full,
        "adres": venue_full,
        "wojewodztwo": woj,
        "organizator": value_prefix(lines, ["Organizator"]),
        "kontakt": value_prefix(lines, ["Kontakt do organizatora"]),
        "wpisowe": value_prefix(lines, ["Wpisowe"]),
        "system_gier": value_prefix(lines, ["System gier"]),
        "limit_uczestnikow": value_prefix(lines, ["Limit uczestników"]),
        "nawierzchnia": value_prefix(lines, ["Nawierzchnia latem"]),
        "zapisy_url": registration_url(page, page.url),
        "szczegoly_url": page.url,
    }
    return {k: v for k, v in details.items() if v}


def extract_kluby(page, item: dict) -> dict:
    response = page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"HTTP {response.status}")
    page.wait_for_timeout(700)
    lines = text_lines(main_text_from_page(page))

    miejsce = value_prefix(lines, ["Miejsce"])
    klub = value_prefix(lines, ["Klub"])
    details = {
        "miejsce": klub or (miejsce.split(",", 1)[0] if miejsce else ""),
        "adres": miejsce,
        "kategorie": value_prefix(lines, ["Kategorie"]),
        "rangi": value_prefix(lines, ["Rangi"]),
        "wpisowe": value_prefix(lines, ["Wpisowe"]),
        "dyrektor_turnieju": value_prefix(lines, ["Dyrektor turnieju"]),
        "telefon_organizatora": value_prefix(lines, ["Telefon"]),
        "email_organizatora": value_prefix(lines, ["E-mail", "Email"]),
        "start_turnieju": value_prefix(lines, ["Start"]),
        "termin_zgloszen": value_prefix(lines, ["Zapisy"]),
        "cykl_szczegolowy": value_prefix(lines, ["Cykl"]),
        "zapisy_url": registration_url(page, item["url"]),
        "szczegoly_url": item["url"],
    }

    try:
        idx = next(i for i, line in enumerate(lines) if line.casefold() == "dodatkowe informacje")
        desc_lines = []
        for line in lines[idx + 1:idx + 40]:
            if line.casefold() in {"sponsorzy turnieju", "wyróżnione oferty", "wyroznione oferty", "mapa serwisu"}:
                break
            desc_lines.append(line)
        if desc_lines:
            details["opis"] = "\n".join(desc_lines)[:2500]
            desc_flat = " ".join(desc_lines)
            m = re.search(r"limit\s+(?:zgłoszeń|zgloszen|uczestnik(?:ów|ow))\s*(?:to|:)?\s*(\d+)", desc_flat, re.I)
            if m:
                details["limit_uczestnikow"] = m.group(1)
    except StopIteration:
        pass

    contacts = [x for x in [details.get("telefon_organizatora"), details.get("email_organizatora")] if x]
    if contacts:
        details["kontakt"] = " | ".join(contacts)
    return {k: v for k, v in details.items() if v}


def extract_browser(page, item: dict) -> dict:
    if item.get("zrodlo") == "PLT":
        return extract_plt(page, item)
    if item.get("zrodlo") == "Kluby.org":
        return extract_kluby(page, item)
    return {}


def parse_last_success(entry: dict) -> date | None:
    value = entry.get("ostatnie_poprawne_pobranie_utc") or ""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return None


def due_for_refresh(item: dict, entry: dict, today: date) -> bool:
    if entry.get("wersja_parsera") != PARSER_VERSION:
        return True
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
        "telefon_organizatora", "email_organizatora", "kontakt", "cykl_szczegolowy",
        "dyrektor_turnieju", "sedzia_naczelny", "pilka", "start_turnieju", "rangi",
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

    due: list[dict] = []
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
            entry["dane"] = details
            entry["wersja_parsera"] = PARSER_VERSION
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
                    entry["dane"] = details
                    entry["wersja_parsera"] = PARSER_VERSION
                    entry["ostatnie_poprawne_pobranie_utc"] = now_iso()
                    entry.pop("ostatni_blad", None)
                    success += 1
                except Exception as exc:
                    entry["ostatni_blad"] = f"{type(exc).__name__}: {exc}"
                    failed += 1
                page.wait_for_timeout(500)
            browser.close()

    for item in items:
        event_id = str(item.get("id"))
        details = cache.get(event_id, {}).get("dane", {})
        merge_details(item, details)
        if clean(item.get("miasto")).casefold() == "kamień" and item.get("zrodlo") == "PLT" and not details.get("wojewodztwo"):
            item["wojewodztwo"] = ""

    # Po danych źródłowych przeliczamy regiony jeszcze raz. Dzięki temu np. PLT
    # może rozstrzygnąć niejednoznaczny Kamień, mimo że geokoder słusznie odmówił.
    calendar["liczba_turniejow_bez_wojewodztwa"] = sum(1 for item in items if not item.get("wojewodztwo"))
    unresolved = load_json(UNRESOLVED_FILE, {"miasta": []})
    resolved_cities = {clean(item.get("miasto")) for item in items if item.get("wojewodztwo")}
    unresolved["miasta"] = [x for x in unresolved.get("miasta", []) if clean(x.get("miasto")) not in resolved_cities]
    unresolved["liczba_nierozpoznanych_miast"] = len(unresolved["miasta"])
    unresolved["aktualizacja_utc"] = now_iso()
    UNRESOLVED_FILE.write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cache_payload["aktualizacja_utc"] = now_iso()
    cache_payload["wersja_parsera"] = PARSER_VERSION
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
