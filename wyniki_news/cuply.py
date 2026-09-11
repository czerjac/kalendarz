"""Cuply adapter: public Livewire tournament results -> normalized sporting data."""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

HOSTS = {"cuply.pl", "www.cuply.pl"}
UA = "Mozilla/5.0 (compatible; TenisNET/1.0; +https://www.tenis.net.pl/)"
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)")
WO_RE = re.compile(r"(?<!\w)w\s*[./]?\s*o\.?(?!\w)|\bwalk(?:over|ower)\b", re.I)
ACTIVE_GROUP_RE = re.compile(r"setActiveGroup\(['\"]([^'\"]+)['\"]\)", re.I)


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def fold(value) -> str:
    text = clean(value).casefold().replace("ł", "l")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def validate_url(url: str) -> str:
    u = urlparse(clean(url))
    if u.scheme != "https" or u.hostname not in HOSTS:
        raise ValueError("Nieprawidłowy adres Cuply")
    parts = [x for x in u.path.split("/") if x]
    if len(parts) != 2 or parts[0] != "turnieje" or not parts[1]:
        raise ValueError("Brak adresu turnieju Cuply")
    return parts[1]


def source_player(anchor) -> dict | None:
    href = clean(anchor.get("href"))
    u = urlparse(href)
    parts = [x for x in u.path.split("/") if x]
    if u.hostname not in HOSTS or len(parts) != 2 or parts[0] != "zawodnicy":
        return None
    slug = parts[1]
    name = clean(anchor.get_text(" ", strip=True))
    return {"id": "cuply:" + slug, "id_zrodlowe": slug, "nazwa": name}


def name_player(name: str) -> dict:
    name = clean(name)
    pid = hashlib.sha1(fold(name).encode()).hexdigest()[:18]
    return {"id": "cuply-nazwa:" + pid, "id_zrodlowe": "nazwa:" + pid, "nazwa": name}


def side(people: list[dict]) -> dict | None:
    unique = []
    seen = set()
    for person in people:
        if not person or not person.get("id") or not person.get("nazwa") or person["id"] in seen:
            continue
        seen.add(person["id"])
        unique.append(person)
    if len(unique) not in (1, 2):
        return None
    typ = "para" if len(unique) == 2 else "osoba"
    sid = "|".join(x["id_zrodlowe"] for x in unique)
    return {"id": f"{typ}:cuply:{sid}", "id_zrodlowe": sid, "typ": typ,
            "zawodnicy": [{"id": x["id"], "nazwa": x["nazwa"]} for x in unique]}


def split_participants(cell) -> tuple[dict | None, dict | None]:
    by_slug = {}
    order = []
    for a in cell.find_all("a", href=True):
        p = source_player(a)
        if not p:
            continue
        key = p["id"]
        if key not in by_slug:
            by_slug[key] = p
            order.append(key)
        elif p["nazwa"] and not by_slug[key]["nazwa"]:
            by_slug[key]["nazwa"] = p["nazwa"]
    people = [by_slug[k] for k in order if by_slug[k].get("nazwa")]
    if len(people) == 2:
        return side([people[0]]), side([people[1]])
    if len(people) == 4:
        return side(people[:2]), side(people[2:])

    text = clean(cell.get_text(" ", strip=True))
    parts = re.split(r"\s+vs\.?\s+", text, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None, None
    fallback = []
    for part in parts:
        names = [clean(x) for x in re.split(r"\s+/\s+", part) if clean(x)]
        fallback.append(side([name_player(x) for x in names[:2]]))
    return fallback[0], fallback[1]


def source_winner(cell) -> str | None:
    """Read Cuply's own winner highlight from the desktop participant row."""
    desktop = cell.find("div", recursive=False)
    root = desktop or cell
    participant_spans = []
    for span in root.find_all("span", recursive=False):
        if any(source_player(a) for a in span.find_all("a", href=True)):
            participant_spans.append(span)
    if len(participant_spans) != 2:
        return None

    flags = []
    for span in participant_spans:
        classes = set(span.get("class") or [])
        marked = "font-bold" in classes or bool(span.find("mark", class_=lambda c: c and "bg-featured" in str(c).split()))
        flags.append(marked)
    if flags == [True, False]:
        return "a"
    if flags == [False, True]:
        return "b"
    return None


def score_parts(cell) -> tuple[list[dict], str, bool, str | None]:
    raw = clean(cell.get_text(" ", strip=True))
    pairs = [(int(a), int(b)) for a, b in SCORE_RE.findall(raw)]
    sets = [{"a": a, "b": b} for a, b in pairs]
    walkover = bool(WO_RE.search(raw))
    winner = None
    if sets:
        aw = sum(x["a"] > x["b"] for x in sets)
        bw = sum(x["b"] > x["a"] for x in sets)
        if aw != bw and not any(x["a"] == x["b"] for x in sets):
            winner = "a" if aw > bw else "b"
    result = ", ".join(f"{x['a']}:{x['b']}" for x in sets)
    if walkover:
        result = (result + " " if result else "") + "(walkower)"
    return sets, result or raw, walkover, winner


def phase_kind(slug: str, label: str) -> str:
    value = fold(slug + " " + label)
    return "grupa" if "grupa" in value else "puchar"


def parse_phase(markup: str, tournament_id: str, slug: str, label: str) -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(markup, "html.parser")
    matches, warnings = [], []
    tables = []
    for table in soup.find_all("table"):
        headers = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
        if "mecz" in headers and "wynik" in headers:
            tables.append(table)
    if not tables:
        return [], [f"{label}: brak tabeli meczów"]

    for table in tables:
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 3:
                continue
            number = clean(cells[0].get_text(" ", strip=True))
            if not number or not re.fullmatch(r"\d+", number):
                continue
            a, b = split_participants(cells[1])
            sets, result, walkover, numeric_winner = score_parts(cells[2])
            highlighted_winner = source_winner(cells[1])
            conflict = bool(highlighted_winner and numeric_winner and highlighted_winner != numeric_winner)
            winner = None if conflict else (highlighted_winner or numeric_winner)
            valid_sides = bool(a and b and a["id"] != b["id"] and a["typ"] == b["typ"])
            score_present = bool(sets or walkover)
            done = bool(valid_sides and winner and score_present and not conflict)

            if conflict:
                warnings.append(f"{label} mecz {number}: oznaczenie zwycięzcy Cuply jest sprzeczne z wynikiem")
            elif walkover and not winner:
                warnings.append(f"{label} mecz {number}: walkower bez jednoznacznego zwycięzcy")
            elif not score_present:
                warnings.append(f"{label} mecz {number}: brak potwierdzonego wyniku")
            elif not winner:
                warnings.append(f"{label} mecz {number}: wynik nie wskazuje zwycięzcy")
            if not valid_sides:
                warnings.append(f"{label} mecz {number}: nie udało się rozpoznać obu stron")

            raw_key = "|".join((str(tournament_id), slug, number,
                                (a or {}).get("id", ""), (b or {}).get("id", ""), result))
            mid = "cuply-mecz:" + hashlib.sha1(raw_key.encode()).hexdigest()[:20]
            matches.append({
                "id": mid,
                "grupa_id": f"cuply:{tournament_id}:{slug}",
                "faza": label,
                "runda": label,
                "typ_fazy": phase_kind(slug, label),
                "strona_a": a,
                "strona_b": b,
                "sety": sets,
                "wynik": result,
                "walkower": walkover,
                "zwyciezca": winner,
                "zakonczony": done,
                "data_zrodlowa": clean(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else None,
                "kort": clean(cells[4].get_text(" ", strip=True)) if len(cells) > 4 else None,
                "nr_meczu_zrodlowy": number,
            })
    return matches, warnings


def phase_buttons(markup: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(markup, "html.parser")
    out = []
    for node in soup.find_all(attrs={"wire:click": True}):
        raw = html_lib.unescape(clean(node.get("wire:click")))
        m = ACTIVE_GROUP_RE.search(raw)
        if not m:
            continue
        value = (m.group(1), clean(node.get_text(" ", strip=True)))
        if value not in out:
            out.append(value)
    return out


def info_field(soup: BeautifulSoup, label: str) -> str:
    wanted = fold(label).rstrip(":")
    for span in soup.find_all("span"):
        if fold(span.get_text(" ", strip=True)).rstrip(":") != wanted:
            continue
        parent = span.parent
        values = [clean(x.get_text(" ", strip=True)) for x in parent.find_all("span", recursive=False)]
        values = [x for x in values if fold(x).rstrip(":") != wanted and x]
        if values:
            return values[-1]
    return ""


def initial(session, url: str) -> dict:
    slug = validate_url(url)
    r = session.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    script = soup.find("script", attrs={"data-update-uri": True, "data-csrf": True})
    root = soup.find(attrs={"wire:name": "tournament-page-tabs", "wire:snapshot": True})
    if not script or not root:
        raise RuntimeError("Cuply: brak publicznego komponentu wyników")
    update_uri = clean(script.get("data-update-uri"))
    endpoint = urlparse(update_uri)
    if endpoint.scheme != "https" or endpoint.hostname not in HOSTS:
        raise RuntimeError("Cuply: nieprawidłowy endpoint Livewire")
    snapshot = root.get("wire:snapshot", "")
    try:
        state = json.loads(snapshot)
    except ValueError as exc:
        raise RuntimeError("Cuply: nieczytelny snapshot Livewire") from exc
    memo = state.get("memo") or {}
    data = state.get("data") or {}
    expected_path = "turnieje/" + slug
    if clean(memo.get("name")) != "tournament-page-tabs" or clean(memo.get("path")) != expected_path:
        raise RuntimeError("Cuply: komponent dotyczy innego turnieju")
    tid = data.get("tournamentId")
    if not isinstance(tid, int) or tid <= 0:
        raise RuntimeError("Cuply: brak identyfikatora turnieju")
    return {
        "slug": slug,
        "tournament_id": str(tid),
        "token": clean(script.get("data-csrf")),
        "update_uri": update_uri,
        "snapshot": snapshot,
        "typ_gry": info_field(soup, "Typ gry"),
        "poziom": info_field(soup, "Poziom"),
        "system_gier": info_field(soup, "System gier"),
    }


def livewire_call(session, url: str, state: dict, method: str, params: list) -> str:
    payload = {"_token": state["token"], "components": [{
        "snapshot": state["snapshot"], "updates": {},
        "calls": [{"method": method, "params": params, "metadata": {}}],
    }]}
    r = session.post(state["update_uri"], json=payload, timeout=40, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Livewire": "true",
        "Origin": "https://cuply.pl",
        "Referer": url,
    })
    r.raise_for_status()
    try:
        body = r.json()
        component = body["components"][0]
        snapshot = component["snapshot"]
        markup = component.get("effects", {}).get("html", "")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Cuply: nieprawidłowa odpowiedź Livewire") from exc
    if not snapshot or not markup:
        raise RuntimeError("Cuply: pusta odpowiedź Livewire")
    state["snapshot"] = snapshot
    return markup


def fetch(item, session):
    state = initial(session, item["url"])
    results_html = livewire_call(session, item["url"], state, "setTab", ["terminarz-wyniki"])
    phases = phase_buttons(results_html)
    if not phases:
        raise RuntimeError("Cuply: brak faz w zakładce wyników")

    matches, warnings, seen = [], [], set()
    for slug, label in phases:
        markup = livewire_call(session, item["url"], state, "setActiveGroup", [slug])
        parsed, local = parse_phase(markup, state["tournament_id"], slug, label)
        # Empty optional placement tabs are normal on Cuply (for example a configured
        # third-place match that was not played), so only propagate parser warnings
        # when the phase actually exposed match rows.
        if parsed:
            warnings.extend(local)
        for match in parsed:
            if match["id"] in seen:
                warnings.append("Powtórzony identyfikator meczu " + match["id"])
                continue
            seen.add(match["id"])
            matches.append(match)

    finals = [m for m in matches if fold(m["faza"]) in {"final", "finaly"} and m["typ_fazy"] == "puchar"]
    knockout = any(m["typ_fazy"] == "puchar" for m in matches)
    if knockout and (len(finals) != 1 or not finals[0]["zakonczony"]):
        warnings.append("Brak potwierdzonego pojedynczego finału")
    group_ids = {m["grupa_id"] for m in matches if m["typ_fazy"] == "grupa"}
    if not knockout and len(group_ids) != 1:
        warnings.append("Niepotwierdzony format końcowy")
    if not matches or any(not m["zakonczony"] for m in matches):
        warnings.append("Brak części rozegranych meczów lub wyników")

    source_category = clean(item.get("kategoria_zrodla") or item.get("kategoria"))
    if not source_category:
        source_category = "; ".join(x for x in (state["typ_gry"], state["poziom"]) if x)
    return {
        "id": "cuply:" + state["tournament_id"],
        "zrodlo": "Cuply",
        "url": item["url"],
        "nazwa": clean(item.get("nazwa")),
        "kategoria": source_category,
        "data_od": item["data_od"],
        "data_do": item.get("data_do") or item["data_od"],
        "miasto": clean(item.get("miasto")),
        "mecze": matches,
        "final_id": finals[0]["id"] if len(finals) == 1 and finals[0]["zakonczony"] else None,
        "gotowy": bool(matches) and not warnings,
        "uwagi": sorted(set(warnings)),
        "meta_zrodla": {"typ_gry": state["typ_gry"], "poziom": state["poziom"], "system_gier": state["system_gier"]},
    }
