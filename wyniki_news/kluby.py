"""Kluby.org adapter: parse public server-rendered sporting results only."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

HOSTS = {"kluby.org", "www.kluby.org"}
WALKOVER_RE = re.compile(r"\b(?:w\.?o\.?|walkower|krecz|ret\.?)\b", re.I)
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[:\-/]\s*(\d{1,2})(?!\d)")


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def fold(value) -> str:
    text = clean(value).casefold().replace("ł", "l")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def is_phase(value: str) -> bool:
    x = fold(value)
    return bool(re.match(r"^(grupa\s+.+|drabinka.*|1/\d+\s*final.*|polfinal.*|final)$", x))


def source_id(href: str, name: str) -> str:
    path = urlsplit(clean(href)).path.rstrip("/") if href else ""
    if path:
        return path
    return "nazwa:" + hashlib.sha1(fold(name).encode()).hexdigest()[:16]


def people_from_cell(cell) -> list[dict]:
    players, seen = [], set()
    anchors = [a for a in cell.find_all("a", href=True) if clean(a.get_text(" ", strip=True))]
    if anchors:
        raw = [(clean(a.get_text(" ", strip=True)), a.get("href", "")) for a in anchors]
    else:
        raw = [(clean(x), "") for x in cell.stripped_strings if clean(x) and not clean(x).isdigit()]
        if len(raw) <= 1:
            text = clean(cell.get_text(" ", strip=True))
            raw = [(clean(x), "") for x in re.split(r"\s+/\s+|\s*\|\s*", text) if clean(x)]
    for name, href in raw:
        key = (fold(name), clean(href))
        if not name or key in seen:
            continue
        seen.add(key)
        players.append({"id": source_id(href, name), "nazwa": name})
    return players[:2]


def side(cell) -> dict | None:
    players = people_from_cell(cell)
    if not players:
        return None
    typ = "para" if len(players) == 2 else "osoba"
    sid = "|".join(x["id"] for x in players)
    return {"id": f"{typ}:{sid}", "id_zrodlowe": sid, "typ": typ, "zawodnicy": players}


def side_label(value: dict | None) -> str:
    return " / ".join(x["nazwa"] for x in value["zawodnicy"]) if value else ""


def score_sets(text: str) -> list[dict]:
    return [{"a": int(a), "b": int(b)} for a, b in SCORE_RE.findall(clean(text))]


def score_winner(sets: list[dict]) -> str | None:
    if not sets or any(x["a"] == x["b"] for x in sets):
        return None
    aw = sum(x["a"] > x["b"] for x in sets)
    bw = sum(x["b"] > x["a"] for x in sets)
    if aw == bw:
        return None
    return "a" if aw > bw else "b"


def explicit_winner(cell, a: dict | None, b: dict | None) -> str | None:
    text = fold(cell.get_text(" ", strip=True))
    if text in {"1", "a", "gracz 1", "zawodnik 1", "para 1"}:
        return "a"
    if text in {"2", "b", "gracz 2", "zawodnik 2", "para 2"}:
        return "b"
    la, lb = fold(side_label(a)), fold(side_label(b))
    if text and la and (text == la or la in text):
        return "a"
    if text and lb and (text == lb or lb in text):
        return "b"
    winner_people = people_from_cell(cell)
    if winner_people:
        ids = {x["id"] for x in winner_people}
        ai = {x["id"] for x in (a or {}).get("zawodnicy", [])}
        bi = {x["id"] for x in (b or {}).get("zawodnicy", [])}
        if ids and ids <= ai:
            return "a"
        if ids and ids <= bi:
            return "b"
    return None


def category_links(soup: BeautifulSoup, fallback: str) -> list[dict]:
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        q = parse_qs(urlsplit(a.get("href", "")).query)
        cid = clean((q.get("kategoria") or [""])[0])
        if cid:
            found[cid] = clean(a.get_text(" ", strip=True)) or cid
    for option in soup.find_all("option"):
        value = clean(option.get("value"))
        q = parse_qs(urlsplit(value).query) if value else {}
        cid = clean((q.get("kategoria") or [""])[0])
        if not cid and value.isdigit():
            cid = value
        if cid:
            found[cid] = clean(option.get_text(" ", strip=True)) or cid
    if found:
        return [{"id": cid, "nazwa": name} for cid, name in found.items()]
    return [{"id": "", "nazwa": clean(fallback)}]


def with_category(url: str, category_id: str) -> str:
    if not category_id:
        return url
    u = urlsplit(url)
    q = parse_qs(u.query)
    q["kategoria"] = [category_id]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q, doseq=True), u.fragment))


def table_columns(table) -> dict[str, int] | None:
    headers = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
    if not headers:
        return None

    def col(*needles):
        for i, h in enumerate(headers):
            if any(n in h for n in needles):
                return i
        return None

    cols = {
        "round": col("runda"),
        "a": col("gracz 1", "zawodnik 1", "para 1"),
        "b": col("gracz 2", "zawodnik 2", "para 2"),
        "score": col("wynik"),
        "winner": col("wygrany", "zwyciezca"),
    }
    if None in (cols["a"], cols["b"], cols["score"]):
        return None
    return cols


def parse_matches(html: str, tournament_id: str, category_id: str, category_name: str) -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = cols = None
    for candidate in soup.find_all("table"):
        candidate_cols = table_columns(candidate)
        if candidate_cols:
            table, cols = candidate, candidate_cols
            break
    if table is None:
        return [], ["Nie znaleziono tabeli meczów"]

    matches, warnings = [], []
    phase = ""
    seq = 0
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells or all(x.name == "th" for x in cells):
            continue
        texts = [clean(x.get_text(" ", strip=True)) for x in cells]
        max_required = max(cols["a"], cols["b"], cols["score"])
        if len(cells) <= max_required:
            label = clean(" ".join(texts))
            if is_phase(label):
                phase = label
            continue
        round_text = texts[cols["round"]] if cols["round"] is not None and cols["round"] < len(texts) else ""
        if is_phase(round_text):
            phase = round_text
        a, b = side(cells[cols["a"]]), side(cells[cols["b"]])
        if not a or not b:
            continue
        score_raw = texts[cols["score"]]
        sets = score_sets(score_raw)
        inferred = score_winner(sets)
        winner = None
        if cols["winner"] is not None and cols["winner"] < len(cells):
            winner = explicit_winner(cells[cols["winner"]], a, b)
        if winner and inferred and winner != inferred:
            warnings.append("Wynik liczbowy jest sprzeczny z kolumną Wygrany")
        if not winner:
            winner = inferred
        walkover = bool(WALKOVER_RE.search(score_raw))
        done = bool(winner and (score_raw or walkover))
        seq += 1
        current_phase = phase or round_text or "Mecze"
        fp = "|".join([category_id, current_phase, round_text, side_label(a), side_label(b), score_raw, str(seq)])
        mid = "kluby-mecz:" + hashlib.sha1(fp.encode()).hexdigest()[:20]
        phase_folded = fold(current_phase)
        typ = "grupa" if phase_folded.startswith("grupa") else "puchar" if ("final" in phase_folded or "drabinka" in phase_folded) else "nieznany"
        matches.append({
            "id": mid,
            "grupa_id": f"kluby:{tournament_id}:{category_id or 'default'}:{phase_folded}",
            "faza": current_phase,
            "runda": round_text,
            "typ_fazy": typ,
            "strona_a": a,
            "strona_b": b,
            "sety": sets,
            "wynik": score_raw,
            "walkower": walkover,
            "zwyciezca": winner,
            "zakonczony": done,
            "data_zrodlowa": None,
            "kategoria_zrodlowa": category_name,
        })
    if not matches:
        warnings.append("Nie znaleziono rozegranych meczów")
    if any(not x["zakonczony"] for x in matches):
        warnings.append("Brak części rozegranych meczów lub wyników")
    return matches, warnings


def parse_standings(html: str) -> list[dict]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        headers = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
        joined = " | ".join(headers)
        if "miejsce" not in joined or "gracz" not in joined:
            continue
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 3:
                continue
            people = people_from_cell(cells[1])
            if people:
                texts = [clean(x.get_text(" ", strip=True)) for x in cells]
                rows.append({"pozycja": texts[0], "zawodnicy": people, "miejsce": texts[2], "etap": texts[3] if len(texts) > 3 else ""})
        if rows:
            return rows
    return []


def participant_names(side_value: dict | None) -> set[str]:
    return {fold(x["nazwa"]) for x in (side_value or {}).get("zawodnicy", []) if clean(x.get("nazwa"))}


def final_sides(match: dict) -> tuple[set[str], set[str]]:
    winner_key = match.get("zwyciezca")
    if winner_key not in {"a", "b"}:
        return set(), set()
    loser_key = "b" if winner_key == "a" else "a"
    return participant_names(match.get("strona_" + winner_key)), participant_names(match.get("strona_" + loser_key))


def final_id(matches: list[dict], standings: list[dict], warnings: list[str]) -> str | None:
    finals = [x for x in matches if fold(x["faza"]) == "final" or fold(x.get("runda")) == "final"]
    completed = [x for x in finals if x.get("zakonczony")]
    if not finals:
        return None
    if not completed:
        warnings.append("Brak zakończonego finału")
        return None

    # Kluby.org może publikować kilka drabinek (np. o różne miejsca), każdą z własnym
    # wierszem „finał”. Gdy jest ich kilka, końcowa kolejność wskazuje finał główny.
    if len(completed) > 1:
        if len(standings) < 2:
            warnings.append("Wiele finałów i brak końcowej kolejności do rozstrzygnięcia")
            return None
        first = {fold(x["nazwa"]) for x in standings[0]["zawodnicy"]}
        second = {fold(x["nazwa"]) for x in standings[1]["zawodnicy"]}
        matching = []
        for candidate in completed:
            winner_names, loser_names = final_sides(candidate)
            if winner_names == first and loser_names == second:
                matching.append(candidate)
        if len(matching) == 1:
            return matching[0]["id"]
        if not matching:
            warnings.append("Żaden z finałów nie zgadza się z końcową kolejnością")
        else:
            warnings.append("Więcej niż jeden finał zgadza się z końcową kolejnością")
        return None

    final = completed[0]
    if len(standings) >= 2:
        winner_names, loser_names = final_sides(final)
        first = {fold(x["nazwa"]) for x in standings[0]["zawodnicy"]}
        second = {fold(x["nazwa"]) for x in standings[1]["zawodnicy"]}
        if winner_names != first:
            warnings.append("Zwycięzca finału jest sprzeczny z końcową kolejnością")
        if loser_names != second:
            warnings.append("Finalista jest sprzeczny z końcową kolejnością")
        if winner_names != first or loser_names != second:
            return None
    return final["id"]


def get(session, url: str, optional: bool = False) -> str:
    r = session.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0 (compatible; TenisNET/1.0; +https://www.tenis.net.pl/)"})
    if optional and r.status_code == 404:
        return ""
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    text = r.text
    low = text.casefold()
    if any(x in low for x in ("captcha", "403 forbidden", "access denied", "cloudflare")):
        raise RuntimeError("Kluby.org zablokowało pobranie wyników")
    return text


def fetch(item, session):
    u = urlsplit(item["url"])
    if u.scheme != "https" or u.hostname not in HOSTS:
        raise ValueError("Nieprawidłowy adres Kluby.org")
    m = re.match(r"^/turnieje/(\d+)(?:/.*)?$", u.path.rstrip("/"))
    if not m:
        raise ValueError("Brak identyfikatora turnieju Kluby.org")
    tid = m.group(1)
    base = f"https://kluby.org/turnieje/{tid}"
    matches_url = base + "/mecze"
    first_html = get(session, matches_url)
    soup = BeautifulSoup(first_html, "html.parser")
    fallback = item.get("kategoria_zrodla") or item.get("kategoria") or item.get("kategorie") or ""
    categories = category_links(soup, fallback)

    all_matches, warnings, finals, names = [], [], [], []
    for cat in categories:
        names.append(cat["nazwa"] or cat["id"])
        html_matches = first_html if not cat["id"] else get(session, with_category(matches_url, cat["id"]))
        matches, local = parse_matches(html_matches, tid, cat["id"], cat["nazwa"])
        all_matches.extend(matches)
        warnings.extend(f"{cat['nazwa'] or cat['id']}: {x}" for x in local)
        standings = parse_standings(get(session, with_category(base + "/kolejnosc", cat["id"]), optional=True))
        fid = final_id(matches, standings, warnings)
        if fid:
            finals.append(fid)

    if len(categories) > 1:
        warnings.append("Turniej wielokategoriowy — news wymaga kontroli redakcyjnej")
    single_final = finals[0] if len(categories) == 1 and len(finals) == 1 else None
    if len(categories) == 1 and any(x["typ_fazy"] == "puchar" for x in all_matches) and not single_final:
        warnings.append("Brak potwierdzonego finału")
    if not all_matches:
        warnings.append("Brak wyników meczów")

    return {
        "id": "kluby:" + tid,
        "zrodlo": "Kluby.org",
        "url": item["url"],
        "nazwa": str(item.get("nazwa") or clean(soup.title.get_text(" ", strip=True) if soup.title else "")),
        "kategoria": ", ".join(x for x in names if x) or str(fallback),
        "data_od": item["data_od"],
        "data_do": item.get("data_do") or item["data_od"],
        "miasto": str(item.get("miasto") or ""),
        "mecze": all_matches,
        "final_id": single_final,
        "gotowy": bool(all_matches) and not warnings,
        "uwagi": sorted(set(warnings)),
    }
