"""Kluby.org results adapter: parse public server-rendered sporting results only."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

HOSTS = {"kluby.org", "www.kluby.org"}
STRUCTURAL = re.compile(r"^(grupa\s+.+|drabinka.*|1/\d+\s*fina.*|p[oó]łfina.*|finał|final)$", re.I)
WALKOVER = re.compile(r"\b(?:w\.?o\.?|walkower|krecz|ret\.?|withdrawal)\b", re.I)
SCORE_PAIR = re.compile(r"(?<!\d)(\d{1,2})\s*[:\-/]\s*(\d{1,2})(?!\d)")


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def fold(value: str) -> str:
    return clean(value).casefold().replace("ł", "l")


def source_id_from_href(href: str, fallback: str) -> str:
    href = clean(href)
    if href:
        path = urlsplit(href).path.rstrip("/")
        if path:
            return path
    return "nazwa:" + hashlib.sha1(fold(fallback).encode("utf-8")).hexdigest()[:16]


def player_nodes(cell) -> list[dict]:
    out, seen = [], set()
    anchors = [a for a in cell.find_all("a", href=True) if clean(a.get_text(" ", strip=True))]
    if anchors:
        raw = [(clean(a.get_text(" ", strip=True)), a.get("href", "")) for a in anchors]
    else:
        raw = []
        for part in cell.stripped_strings:
            text = clean(part)
            if text and not text.isdigit():
                raw.append((text, ""))
        if len(raw) <= 1:
            text = clean(cell.get_text(" ", strip=True))
            split = [clean(x) for x in re.split(r"\s+/\s+|\s*\|\s*", text) if clean(x)]
            raw = [(x, "") for x in split]
    for name, href in raw:
        key = (fold(name), clean(href))
        if not name or key in seen:
            continue
        seen.add(key)
        out.append({"id": source_id_from_href(href, name), "nazwa": name})
    return out[:2]


def side(cell) -> dict | None:
    players = player_nodes(cell)
    if not players:
        return None
    typ = "para" if len(players) == 2 else "osoba"
    sid = "|".join(p["id"] for p in players)
    return {"id": f"{typ}:{sid}", "id_zrodlowe": sid, "typ": typ, "zawodnicy": players}


def side_label(value: dict | None) -> str:
    return " / ".join(p["nazwa"] for p in value["zawodnicy"]) if value else ""


def explicit_winner(cell, a: dict | None, b: dict | None) -> str | None:
    text = fold(cell.get_text(" ", strip=True))
    if text in {"1", "a", "gracz 1", "zawodnik 1", "para 1"}:
        return "a"
    if text in {"2", "b", "gracz 2", "zawodnik 2", "para 2"}:
        return "b"
    if not text:
        return None
    la, lb = fold(side_label(a)), fold(side_label(b))
    if la and (text == la or la in text):
        return "a"
    if lb and (text == lb or lb in text):
        return "b"
    winner_people = player_nodes(cell)
    if winner_people:
        ids = {p["id"] for p in winner_people}
        ai = {p["id"] for p in (a or {}).get("zawodnicy", [])}
        bi = {p["id"] for p in (b or {}).get("zawodnicy", [])}
        if ids and ids <= ai:
            return "a"
        if ids and ids <= bi:
            return "b"
    return None


def score_sets(text: str) -> list[dict]:
    return [{"a": int(a), "b": int(b)} for a, b in SCORE_PAIR.findall(clean(text))]


def infer_winner_from_score(sets: list[dict]) -> str | None:
    if not sets or any(s["a"] == s["b"] for s in sets):
        return None
    aw = sum(s["a"] > s["b"] for s in sets)
    bw = sum(s["b"] > s["a"] for s in sets)
    if aw == bw:
        return None
    return "a" if aw > bw else "b"


def structural_label(text: str) -> str | None:
    value = clean(text)
    return value if value and STRUCTURAL.match(value) else None


def category_links(soup: BeautifulSoup, page_url: str, fallback: str) -> list[dict]:
    found = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        q = parse_qs(urlsplit(href).query)
        cid = clean((q.get("kategoria") or [""])[0])
        if cid:
            found[cid] = clean(a.get_text(" ", strip=True)) or cid
    for option in soup.find_all("option"):
        value = clean(option.get("value"))
        cid = ""
        if value:
            q = parse_qs(urlsplit(value).query)
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


def find_match_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        heads = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
        joined = " | ".join(heads)
        if "gracz 1" in joined and "gracz 2" in joined and "wynik" in joined:
            return table
    return None


def parse_matches(html: str, tournament_id: str, category_id: str, category_name: str) -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = find_match_table(soup)
    if table is None:
        return [], ["Nie znaleziono tabeli meczów"]
    headers = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
    index = {name: i for i, name in enumerate(headers)}
    def col(*needles):
        for i, h in enumerate(headers):
            if any(n in h for n in needles):
                return i
        return None
    i_round = col("runda")
    i_a = col("gracz 1", "zawodnik 1", "para 1")
    i_b = col("gracz 2", "zawodnik 2", "para 2")
    i_score = col("wynik")
    i_winner = col("wygrany", "zwyciezca")
    if None in (i_a, i_b, i_score):
        return [], ["Nie rozpoznano kolumn tabeli meczów"]

    matches, warnings, seen = [], [], set()
    context = ""
    sequence = 0
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells or all(c.name == "th" for c in cells):
            continue
        texts = [clean(c.get_text(" ", strip=True)) for c in cells]
        if len(cells) == 1 or (len(cells) < max(i_a, i_b, i_score) + 1):
            label = structural_label(" ".join(texts))
            if label:
                context = label
            continue
        round_text = texts[i_round] if i_round is not None and i_round < len(texts) else ""
        if structural_label(round_text):
            context = round_text
        a, b = side(cells[i_a]), side(cells[i_b])
        score_raw = texts[i_score]
        if not a or not b:
            continue
        winner = explicit_winner(cells[i_winner], a, b) if i_winner is not None and i_winner < len(cells) else None
        sets = score_sets(score_raw)
        inferred = infer_winner_from_score(sets)
        if winner and inferred and winner != inferred:
            warnings.append("Wynik liczbowy jest sprzeczny z kolumną Wygrany")
        if not winner:
            winner = inferred
        walkover = bool(WALKOVER.search(score_raw))
        done = bool(winner and (score_raw or walkover))
        sequence += 1
        fingerprint = "|".join([category_id, context, round_text, side_label(a), side_label(b), score_raw, str(sequence)])
        mid = "kluby-mecz:" + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:20]
        if mid in seen:
            warnings.append("Powtórzony identyfikator meczu")
        seen.add(mid)
        phase = context or round_text or "Mecze"
        typ = "grupa" if fold(phase).startswith("grupa") else "puchar" if any(x in fold(phase) for x in ("final", "drabinka")) else "nieznany"
        matches.append({
            "id": mid,
            "grupa_id": f"kluby:{tournament_id}:{category_id or 'default'}:{fold(phase)}",
            "faza": phase,
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
    if any(not m["zakonczony"] for m in matches):
        warnings.append("Brak części rozegranych meczów lub wyników")
    return matches, warnings


def parse_standings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        heads = [fold(x.get_text(" ", strip=True)) for x in table.find_all("th")]
        joined = " | ".join(heads)
        if "miejsce" not in joined or "gracz" not in joined:
            continue
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 3:
                continue
            texts = [clean(c.get_text(" ", strip=True)) for c in cells]
            people = player_nodes(cells[1])
            if not people:
                continue
            rows.append({"pozycja": texts[0], "zawodnicy": people, "miejsce": texts[2], "etap": texts[3] if len(texts) > 3 else ""})
        if rows:
            return rows
    return []


def validate_final(matches: list[dict], standings: list[dict], warnings: list[str]) -> str | None:
    finals = [m for m in matches if fold(m["faza"]) in {"final", "final."} or fold(m.get("runda")) in {"final", "final."}]
    if not finals:
        return None
    if len(finals) != 1 or not finals[0]["zakonczony"]:
        warnings.append("Brak potwierdzonego pojedynczego finału")
        return None
    final = finals[0]
    if len(standings) >= 2:
        winner = final["strona_" + final["zwyciezca"]]
        loser = final["strona_" + ("b" if final["zwyciezca"] == "a" else "a")]
        wnames = {fold(p["nazwa"]) for p in winner["zawodnicy"]}
        lnames = {fold(p["nazwa"]) for p in loser["zawodnicy"]}
        s1 = {fold(p["nazwa"]) for p in standings[0]["zawodnicy"]}
        s2 = {fold(p["nazwa"]) for p in standings[1]["zawodnicy"]}
        if wnames != s1 or lnames != s2:
            warnings.append("Finał jest sprzeczny z końcową kolejnością")
    return final["id"]


def fetch_page(session, url: str, required: bool = True) -> str:
    r = session.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0 (compatible; TenisNET/1.0; +https://www.tenis.net.pl/)"})
    if not required and r.status_code == 404:
        return ""
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    text = r.text
    low = text.casefold()
    if any(token in low for token in ("captcha", "403 forbidden", "access denied", "cloudflare")):
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
    first_url = base + "/mecze"
    first_html = fetch_page(session, first_url)
    soup = BeautifulSoup(first_html, "html.parser")
    fallback = item.get("kategoria_zrodla") or item.get("kategoria") or item.get("kategorie") or ""
    categories = category_links(soup, first_url, fallback)

    all_matches, warnings, finals = [], [], []
    category_names = []
    for cat in categories:
        category_names.append(cat["nazwa"] or cat["id"])
        match_url = with_category(first_url, cat["id"])
        html_matches = first_html if not cat["id"] else fetch_page(session, match_url)
        matches, local = parse_matches(html_matches, tid, cat["id"], cat["nazwa"])
        all_matches.extend(matches)
        warnings.extend(f"{cat['nazwa'] or cat['id']}: {x}" for x in local)
        standings_url = with_category(base + "/kolejnosc", cat["id"])
        standings_html = fetch_page(session, standings_url, required=False)
        standings = parse_standings(standings_html) if standings_html else []
        final_id = validate_final(matches, standings, warnings)
        if final_id:
            finals.append(final_id)

    if len(categories) > 1:
        warnings.append("Turniej wielokategoriowy — news wymaga kontroli redakcyjnej")
    final_id = finals[0] if len(categories) == 1 and len(finals) == 1 else None
    if len(categories) == 1 and any(m["typ_fazy"] == "puchar" for m in all_matches) and not final_id:
        warnings.append("Brak potwierdzonego finału")
    if not all_matches:
        warnings.append("Brak wyników meczów")

    return {
        "id": "kluby:" + tid,
        "zrodlo": "Kluby.org",
        "url": item["url"],
        "nazwa": str(item.get("nazwa") or clean(soup.title.get_text(" ", strip=True) if soup.title else "")),
        "kategoria": ", ".join(x for x in category_names if x) or str(fallback),
        "data_od": item["data_od"],
        "data_do": item.get("data_do") or item["data_od"],
        "miasto": str(item.get("miasto") or ""),
        "mecze": all_matches,
        "final_id": final_id,
        "gotowy": bool(all_matches) and not warnings,
        "uwagi": sorted(set(warnings)),
    }
