from __future__ import annotations

import calendar
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

import cuply
import kluby
import plt
import skanda

YEAR = 2026
TODAY = date.today()
ROOT = Path(f"data/archiwum/{YEAR}")
SOURCES_DIR = ROOT / "zrodla"
OUTPUT_FILE = ROOT / "turnieje.json"
REPORT_FILE = ROOT / "raport.json"
DUP_FILE = ROOT / "duplikaty_do_weryfikacji.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
    )
}
PZT_RESULTS_URL = "https://portal.pzt.pl/TournamentsResults.aspx?CategoryID=AIS"
PZT_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})\s*-\s*(20\d{2}-\d{2}-\d{2})")
YOUTH_RE = re.compile(r"\b(JUNIORZY|JUNIORKI|TENIS10|U1[02468])\b", re.I)
PZT_LEAGUE_RE = re.compile(r"\b(liga|challenge|challange|drabinka|ladder)\b", re.I)


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


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ascii_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold().replace("ł", "l")


def normalized_name(value: str) -> str:
    value = ascii_text(value)
    value = re.sub(r"\b(?:puchar plt|plt kobiet|1\.? liga|2\.? liga|top pzt tour)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def specific_url(source: str, url: str) -> bool:
    path = urlparse(url or "").path.rstrip("/")
    if source == "TKKF Skanda":
        return False
    if source == "Kluby.org":
        return bool(re.fullmatch(r"/turnieje/\d+", path))
    if source == "PZT TOP":
        return "TournamentResults.aspx" in (url or "")
    if source in {"Cuply", "PLT"}:
        return "/turnieje/" in path and not path.endswith("lista-rund") and path != "/turnieje"
    return bool(url)


def source_key(item: dict) -> str:
    source = clean(item.get("zrodlo"))
    url = clean(item.get("url"))
    if url and specific_url(source, url):
        identity = f"{source}|{url}"
    else:
        identity = f"{source}|{clean(item.get('nazwa'))}|{clean(item.get('data_od'))}|{clean(item.get('miasto'))}"
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:18]


def merge_cumulative(path: Path, source: str, new_items: list[dict], metadata: dict | None = None) -> list[dict]:
    previous = load_json(path, {"turnieje": []})
    merged: dict[str, dict] = {}
    for raw in previous.get("turnieje", []):
        item = dict(raw)
        item.setdefault("klucz_zrodla", source_key(item))
        merged[item["klucz_zrodla"]] = item

    seen_now: set[str] = set()
    for raw in new_items:
        item = dict(raw)
        key = source_key(item)
        seen_now.add(key)
        old = merged.get(key, {})
        first_seen = old.get("pierwsze_wykrycie_utc") or now_iso()
        item["klucz_zrodla"] = key
        item["pierwsze_wykrycie_utc"] = first_seen
        item["ostatnio_widziany_utc"] = now_iso()
        item["aktywny_w_zrodle_przy_ostatnim_odczycie"] = True
        merged[key] = item

    # Archiwum jest kumulacyjne: brak na stronie nie usuwa historycznego rekordu.
    for key, item in merged.items():
        if key not in seen_now:
            item["aktywny_w_zrodle_przy_ostatnim_odczycie"] = False

    items = sorted(merged.values(), key=lambda x: (clean(x.get("data_od")), clean(x.get("miasto")), clean(x.get("nazwa"))))
    payload = {
        "zrodlo": source,
        "rok": YEAR,
        "aktualizacja_utc": now_iso(),
        "liczba_rekordow": len(items),
        "liczba_widzianych_w_tym_odczycie": len(seen_now),
        "turnieje": items,
    }
    if metadata:
        payload.update(metadata)
    save_json(path, payload)
    return items


def past_2026(item: dict) -> bool:
    start = clean(item.get("data_od"))
    end = clean(item.get("data_do")) or start
    if not start.startswith(f"{YEAR}-"):
        return False
    try:
        return date.fromisoformat(end) < TODAY
    except ValueError:
        return False


# ---------- PZT ----------

def fetch_pzt() -> tuple[list[dict], dict]:
    r = requests.get(PZT_RESULTS_URL, timeout=40, headers=HEADERS)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    items: list[dict] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 4:
            continue
        lp = clean(cells[0].get_text(" ", strip=True))
        if not lp.isdigit():
            continue
        row_text = clean(row.get_text(" ", strip=True))
        m = PZT_DATE_RE.search(row_text)
        if not m or not m.group(1).startswith(f"{YEAR}-"):
            continue
        start, end = m.groups()
        try:
            if date.fromisoformat(end) >= TODAY:
                continue
        except ValueError:
            continue
        link = row.find("a", href=True)
        if not link:
            continue
        href = urljoin(PZT_RESULTS_URL, link["href"])
        if "TournamentResults.aspx" not in href:
            continue
        status = clean(cells[-2].get_text(" ", strip=True)) if len(cells) >= 4 else ""
        name = clean(link.get_text(" ", strip=True))
        items.append({
            "zrodlo": "PZT TOP",
            "cykl_szczegolowy": "TOP PZT",
            "nazwa": name,
            "data_od": start,
            "data_do": end,
            "miasto": "",
            "status_zrodla": status,
            "url": href,
        })
    return items, {"adres_zrodla": PZT_RESULTS_URL}


# ---------- Cuply ----------

def cuply_items_from_html(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    by_url: dict[str, dict] = {}
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(page_url, anchor["href"])
        parsed = urlparse(absolute)
        path = parsed.path.rstrip("/")
        if parsed.netloc not in {"cuply.pl", "www.cuply.pl"} or not path.startswith("/turnieje/"):
            continue
        name = clean(anchor.get_text(" ", strip=True))
        if not name or name.casefold().startswith(cuply.CTA_PREFIXES) or name.casefold().startswith("zobacz wyniki"):
            continue
        card = cuply.find_card(anchor)
        if card is None:
            continue
        card_text = clean(card.get_text(" ", strip=True))
        dates = cuply.parse_date_range(card_text)
        if not dates:
            continue
        start, end = dates
        date_warning = ""
        try:
            parsed_start = date.fromisoformat(start)
            parsed_end = date.fromisoformat(end)
            if parsed_start.year == YEAR - 1 and parsed_end.year == YEAR and (parsed_end - parsed_start).days > 180:
                raw = re.search(r"Termin:\s*(\d{1,2})\.(\d{1,2}).*?-\s*(\d{1,2})\.(\d{1,2})\.%d" % YEAR, card_text, re.I)
                if raw and raw.group(1) == raw.group(3):
                    corrected = date(YEAR, int(raw.group(2)), int(raw.group(1)))
                    start = corrected.isoformat()
                    end = corrected.isoformat()
                    date_warning = "niespojny_zakres_dat_w_zrodle"
        except ValueError:
            pass

        if not start.startswith(f"{YEAR}-"):
            continue
        try:
            if date.fromisoformat(end) >= TODAY:
                continue
        except ValueError:
            continue

        place_match = re.search(
            r"Miejsce:\s*(.+?)(?=\s+(?:Zobacz wyniki|Weź udział|Wez udzial|Zapisz się|Zapisz sie|Zapisy od|$))",
            card_text,
            re.I,
        )
        place = clean(place_match.group(1)) if place_match else cuply.extract_place(card_text)
        item = {
            "zrodlo": "Cuply",
            "cykl_szczegolowy": "Cuply",
            "nazwa": name,
            "data_od": start,
            "data_do": end,
            "miasto": cuply.extract_city(place),
            "miejsce": place,
            "url": absolute,
            "status_zrodla": "Zakończone",
        }
        if date_warning:
            item["uwaga_zrodla"] = date_warning
        by_url[absolute] = item
    return list(by_url.values())


def fetch_cuply(page) -> tuple[list[dict], dict]:
    all_items: dict[str, dict] = {}
    checked: list[dict] = []
    previous_page_keys: set[str] = set()

    for page_no in range(1, 31):
        url = f"https://cuply.pl/turnieje?sortuj=zakonczone&page={page_no}"
        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        if response is not None and response.status >= 400:
            raise RuntimeError(f"Cuply HTTP {response.status}: {url}")
        page.wait_for_timeout(900)
        items = cuply_items_from_html(page.content(), url)
        if not items:
            page.reload(wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            items = cuply_items_from_html(page.content(), url)
        keys = {clean(x.get("url")) for x in items}
        checked.append({"strona": page_no, "url": url, "liczba": len(items)})
        if not items:
            break
        if page_no > 1 and keys and keys == previous_page_keys:
            break
        new_count = 0
        for item in items:
            if item["url"] not in all_items:
                new_count += 1
            all_items[item["url"]] = item
        if page_no > 1 and new_count == 0:
            break
        previous_page_keys = keys
    return list(all_items.values()), {"strony_sprawdzone": checked}


# ---------- PLT ----------

def dismiss_plt_consent(page) -> None:
    try:
        loc = page.get_by_text("Przejdź do serwisu", exact=True)
        if loc.count():
            loc.last.click(timeout=5000)
            page.wait_for_timeout(1200)
    except Exception:
        pass


def next_numeric_page(page, number: int) -> bool:
    pattern = re.compile(rf"^\s*{number}\s*$")
    loc = page.locator("a,button").filter(has_text=pattern)
    for i in range(loc.count() - 1, -1, -1):
        try:
            if loc.nth(i).is_visible():
                loc.nth(i).click(timeout=5000)
                page.wait_for_timeout(1600)
                return True
        except Exception:
            continue
    return False


def fetch_plt(page) -> tuple[list[dict], dict]:
    all_items: dict[str, dict] = {}
    checked: list[dict] = []
    consent_done = False

    for category, base_url in plt.FALLBACK_CATEGORIES.items():
        if not consent_done:
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            dismiss_plt_consent(page)
            consent_done = True
        url = f"{base_url}?finished=true"
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        dismiss_plt_consent(page)

        page_no = 1
        category_count = 0
        seen_page_signatures: set[tuple[str, ...]] = set()
        while page_no <= 60:
            items = plt.extract_cards(page, category)
            items = [x for x in items if past_2026(x)]
            signature = tuple(sorted(clean(x.get("url")) for x in items))
            if signature in seen_page_signatures:
                break
            seen_page_signatures.add(signature)
            for item in items:
                item["status_zrodla"] = "Zakończone"
                all_items[clean(item.get("url")) or source_key(item)] = item
            category_count += len(items)
            if not next_numeric_page(page, page_no + 1):
                break
            page_no += 1
        checked.append({"kategoria": category, "url": url, "liczba": category_count, "strony": page_no})
    return list(all_items.values()), {"kategorie_sprawdzone": checked}


# ---------- Kluby.org ----------

def fetch_kluby(page) -> tuple[list[dict], dict]:
    all_items: dict[str, dict] = {}
    checked: list[dict] = []
    for month in range(1, TODAY.month + 1):
        last = calendar.monthrange(YEAR, month)[1]
        params = {
            "filtr": "1",
            "opcja": "kalendarz",
            "data_od": f"{YEAR}-{month:02d}-01",
            "data_do": f"{YEAR}-{month:02d}-{last:02d}",
            "zakladka": "0",
        }
        url = f"https://kluby.org/tenis/turnieje?{urlencode(params)}"
        response = None
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            # Kluby.org czasem ładuje treść poprawnie, ale nie kończy zdarzenia DOMContentLoaded.
            # Jeśli karta turnieju jest już w DOM, parsujemy ją zamiast odrzucać cały miesiąc.
            pass
        if response is not None and response.status >= 400:
            raise RuntimeError(f"Kluby.org HTTP {response.status}: {url}")
        items = kluby.extract_cards(page, url)
        if not items:
            try:
                page.goto(url, wait_until="commit", timeout=30000)
                page.wait_for_timeout(1600)
                items = kluby.extract_cards(page, url)
            except Exception:
                pass
        kept = 0
        for item in items:
            if not past_2026(item):
                continue
            if YOUTH_RE.search(clean(item.get("kategorie"))):
                continue
            key = clean(item.get("url")) if specific_url("Kluby.org", clean(item.get("url"))) else source_key(item)
            all_items[key] = item
            kept += 1
        checked.append({"miesiac": month, "url": url, "surowe": len(items), "po_filtrach": kept})
    return list(all_items.values()), {"miesiace_sprawdzone": checked}


# ---------- TKKF Skanda ----------

def fetch_skanda() -> tuple[list[dict], dict]:
    soup = skanda.soup_from_url(skanda.TURNIEJE_URL)
    contact = skanda.contact_data()
    year, lines = skanda.schedule_lines(soup)
    if year != YEAR:
        return [], {"rok_harmonogramu": year, "odrzucono_odwolane": 0}

    all_events: list[dict] = []
    cancelled_count = 0
    current_date = ""
    current_time = ""
    bucket: list[str] = []

    def flush() -> None:
        nonlocal bucket, cancelled_count
        if not current_date:
            bucket = []
            return
        parsed, cancelled = skanda.events_from_bucket(current_date, current_time, bucket, contact)
        all_events.extend(parsed)
        cancelled_count += cancelled
        bucket = []

    for line in lines:
        parsed_date = skanda.parse_date_line(line, year)
        if parsed_date:
            flush()
            current_date, current_time = parsed_date
            continue
        if line.casefold().startswith(("harmonogram turniejów do pobrania", "regulamin turniejów", "archiwum turniejów", "cennik ")):
            break
        bucket.append(line)
    flush()
    items = [x for x in all_events if past_2026(x)]
    return items, {"rok_harmonogramu": year, "odrzucono_odwolane": cancelled_count}


# ---------- Wspólne archiwum ----------

def archive_status(item: dict) -> str:
    source = clean(item.get("zrodlo"))
    status = ascii_text(clean(item.get("status_zrodla")))
    if source in {"Cuply", "PLT", "TKKF Skanda"}:
        return "zakonczony_wg_zrodla"
    if "zakoncz" in status or "rozegr" in status:
        return "zakonczony_wg_zrodla"
    return "niezweryfikowany"


def quality_rejection(item: dict) -> list[str]:
    reasons: list[str] = []
    try:
        start = date.fromisoformat(clean(item.get("data_od")))
        end = date.fromisoformat(clean(item.get("data_do")) or clean(item.get("data_od")))
        days = (end - start).days + 1
    except ValueError:
        return ["bledna_data"]
    if end < start:
        reasons.append("data_koncowa_przed_poczatkowa")
    if item.get("zrodlo") == "PZT TOP":
        title = ascii_text(clean(item.get("nazwa")))
        if days >= 15 and PZT_LEAGUE_RE.search(title):
            reasons.append("rozgrywki_ligowe_lub_challenge")
        if days >= 45:
            reasons.append("wydarzenie_wielotygodniowe")
    if item.get("zrodlo") == "Cuply" and days > 14:
        reasons.append("podejrzanie_dlugi_termin_cuply")
    return reasons


def normalize_item(raw: dict) -> dict:
    item = dict(raw)
    source = clean(item.get("zrodlo"))
    key = item.get("klucz_zrodla") or source_key(item)
    item["id"] = hashlib.sha1(f"ARCH2026|{key}".encode("utf-8")).hexdigest()[:14]
    item["klucz_zrodla"] = key
    if source == "PLT":
        item["cykl"] = "PLT"
        item["kategoria_zrodla"] = clean(item.get("kategoria"))
    elif source == "PZT TOP":
        item["cykl"] = "TOP PZT"
    elif source == "Cuply":
        item["cykl"] = "Cuply"
    else:
        item["cykl"] = clean(item.get("cykl_szczegolowy"))
    item["status_archiwum"] = archive_status(item)
    item["uwagi_jakosci"] = quality_rejection(item)
    return item


def duplicate_candidates(items: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if a.get("zrodlo") == b.get("zrodlo"):
                continue
            if clean(a.get("data_od")) != clean(b.get("data_od")):
                continue
            city_a = normalized_name(clean(a.get("miasto")))
            city_b = normalized_name(clean(b.get("miasto")))
            name_a = normalized_name(clean(a.get("nazwa")))
            name_b = normalized_name(clean(b.get("nazwa")))
            if not name_a or not name_b:
                continue
            name_score = SequenceMatcher(None, name_a, name_b).ratio()
            if city_a and city_b:
                if city_a != city_b or name_score < 0.80:
                    continue
            elif name_score < 0.92:
                continue
            candidates.append({
                "id_a": a["id"],
                "id_b": b["id"],
                "zrodlo_a": a.get("zrodlo"),
                "zrodlo_b": b.get("zrodlo"),
                "nazwa_a": a.get("nazwa"),
                "nazwa_b": b.get("nazwa"),
                "data": a.get("data_od"),
                "miasto_a": a.get("miasto"),
                "miasto_b": b.get("miasto"),
                "zgodnosc_nazwy": round(name_score, 3),
            })
    return candidates


def main() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[dict] = []
    source_results: dict[str, list[dict]] = {}

    # Źródła HTTP.
    for source, filename, fn in [
        ("PZT TOP", "pzt.json", fetch_pzt),
        ("TKKF Skanda", "skanda.json", fetch_skanda),
    ]:
        path = SOURCES_DIR / filename
        try:
            new_items, meta = fn()
            source_results[source] = merge_cumulative(path, source, new_items, meta)
            print(f"ARCHIWUM {source}: odczyt {len(new_items)}, kumulacyjnie {len(source_results[source])}")
        except Exception as exc:
            errors.append({"zrodlo": source, "blad": f"{type(exc).__name__}: {exc}"})
            old = load_json(path, {"turnieje": []}).get("turnieje", [])
            source_results[source] = old
            print(f"ARCHIWUM {source}: BŁĄD {exc}; zachowano {len(old)} starych rekordów")

    # Źródła wymagające przeglądarki.
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="pl-PL", user_agent=HEADERS["User-Agent"])
        page = context.new_page()
        page.set_default_timeout(20000)
        for source, filename, fn in [
            ("Cuply", "cuply.json", fetch_cuply),
            ("PLT", "plt.json", fetch_plt),
            ("Kluby.org", "kluby.json", fetch_kluby),
        ]:
            path = SOURCES_DIR / filename
            try:
                new_items, meta = fn(page)
                source_results[source] = merge_cumulative(path, source, new_items, meta)
                print(f"ARCHIWUM {source}: odczyt {len(new_items)}, kumulacyjnie {len(source_results[source])}")
            except Exception as exc:
                errors.append({"zrodlo": source, "blad": f"{type(exc).__name__}: {exc}"})
                old = load_json(path, {"turnieje": []}).get("turnieje", [])
                source_results[source] = old
                print(f"ARCHIWUM {source}: BŁĄD {exc}; zachowano {len(old)} starych rekordów")
        browser.close()

    all_items: list[dict] = []
    for rows in source_results.values():
        for raw in rows:
            if past_2026(raw):
                all_items.append(normalize_item(raw))

    # Nie publikujemy w głównym archiwum rekordów odrzuconych przez mocne reguły jakości,
    # ale pozostają one w plikach źródłowych i są raportowane.
    rejected = [x for x in all_items if x.get("uwagi_jakosci")]
    accepted = [x for x in all_items if not x.get("uwagi_jakosci")]
    accepted.sort(key=lambda x: (clean(x.get("data_od")), clean(x.get("miasto")), clean(x.get("nazwa")), clean(x.get("zrodlo"))))
    duplicates = duplicate_candidates(accepted)

    counts_source = Counter(clean(x.get("zrodlo")) for x in accepted)
    counts_status = Counter(clean(x.get("status_archiwum")) for x in accepted)
    output = {
        "rok": YEAR,
        "aktualizacja_utc": now_iso(),
        "liczba_turniejow_zrodlowych_po_filtrach": len(all_items),
        "liczba_turniejow_po_kontroli_jakosci": len(accepted),
        "liczba_wg_zrodla": dict(sorted(counts_source.items())),
        "liczba_wg_statusu_archiwum": dict(sorted(counts_status.items())),
        "liczba_potencjalnych_par_duplikatow": len(duplicates),
        "turnieje": accepted,
    }
    save_json(OUTPUT_FILE, output)
    save_json(DUP_FILE, {"rok": YEAR, "aktualizacja_utc": now_iso(), "liczba": len(duplicates), "pary": duplicates})
    report = {
        "rok": YEAR,
        "aktualizacja_utc": now_iso(),
        "bledy_zrodel": errors,
        "liczba_rekordow_zrodlowych": {k: len(v) for k, v in source_results.items()},
        "liczba_po_filtrze_dat_i_roku": len(all_items),
        "liczba_odrzuconych_jakosc": len(rejected),
        "odrzucone_jakosc": [
            {"id": x.get("id"), "zrodlo": x.get("zrodlo"), "nazwa": x.get("nazwa"), "data_od": x.get("data_od"), "data_do": x.get("data_do"), "powody": x.get("uwagi_jakosci")}
            for x in rejected
        ],
        "liczba_po_kontroli_jakosci": len(accepted),
        "liczba_potencjalnych_par_duplikatow": len(duplicates),
        "liczba_niezweryfikowanych": sum(1 for x in accepted if x.get("status_archiwum") == "niezweryfikowany"),
    }
    save_json(REPORT_FILE, report)

    print("\n=== PODSUMOWANIE ARCHIWUM 2026 ===")
    print("Rekordy źródłowe:", {k: len(v) for k, v in source_results.items()})
    print("Po filtrze dat:", len(all_items))
    print("Odrzucone jakość:", len(rejected))
    print("W archiwum:", len(accepted))
    print("Według źródła:", dict(counts_source))
    print("Statusy:", dict(counts_status))
    print("Kandydaci duplikatów:", len(duplicates))
    if errors:
        print("Błędy źródeł:", errors)


if __name__ == "__main__":
    main()
