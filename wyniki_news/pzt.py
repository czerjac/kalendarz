"""PZT TOP adapter: normalize public portal.pzt.pl match tables for wyniki_news."""
from __future__ import annotations

import base64
import hashlib
import re
import unicodedata
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

BASE = "https://portal.pzt.pl/"
HOSTS = {"portal.pzt.pl", "www.portal.pzt.pl"}
TOURNAMENT_ID_RE = re.compile(r"^[0-9A-Fa-f-]{20,}$")
MATCH_URL_RE = re.compile(r"['\"](/TournamentMatches\.aspx\?QS=[^'\"]+)['\"]", re.I)
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[:/]\s*(\d{1,2})(?!\d)")
WO_RE = re.compile(r"\bw\.?\s*o\.?\b|walkower", re.I)
RET_RE = re.compile(r"\b(?:ret\.?|krecz)\b", re.I)
SPECIAL_LEFT_WIN_RE = re.compile(r"\bV\s*:\s*0\b", re.I)
RANK_RE = re.compile(r"^(?:1|2|3|3-4|3–4|4|5(?:\s*\(.*\))?)$")


def clean(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def fold(value) -> str:
    text = clean(value).casefold().replace("ł", "l")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def player(name: str) -> dict:
    name = clean(name)
    pid = hashlib.sha1(fold(name).encode()).hexdigest()[:18]
    return {"id": "pzt-nazwa:" + pid, "nazwa": name}


def side_from_names(names: list[str]) -> dict | None:
    names = [clean(x) for x in names if clean(x) and fold(x) != "bye"]
    if not names:
        return None
    # The PZT match table renders doubles partners as separate text nodes in one cell.
    # Keep at most two players; identity resolution across sources is deliberately out of scope.
    people = [player(x) for x in names[:2]]
    typ = "para" if len(people) == 2 else "osoba"
    sid = "|".join(x["id"] for x in people)
    return {"id": f"{typ}:{sid}", "id_zrodlowe": sid, "typ": typ, "zawodnicy": people}


def names_from_cell(cell) -> list[str]:
    return [clean(x) for x in cell.stripped_strings if clean(x)]


def side_names(side: dict | None) -> set[str]:
    return {fold(x["nazwa"]) for x in (side or {}).get("zawodnicy", [])}


def tournament_id(url: str) -> str:
    u = urlsplit(clean(url))
    if u.hostname not in HOSTS:
        raise ValueError("Nieprawidłowy adres PZT TOP")
    tid = clean((parse_qs(u.query).get("TournamentID") or [""])[0])
    if not tid or not TOURNAMENT_ID_RE.match(tid):
        raise ValueError("Brak identyfikatora turnieju PZT")
    return tid.upper()


def decode_qs(url: str) -> dict[str, str]:
    encoded = clean((parse_qs(urlsplit(url).query).get("QS") or [""])[0])
    if not encoded:
        return {}
    try:
        encoded += "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded).decode("utf-8", "replace")
        return {k: clean(v[0]) for k, v in parse_qs(decoded, keep_blank_values=True).items() if v}
    except Exception:
        return {}


def event_id(url: str) -> str:
    decoded = decode_qs(url)
    value = decoded.get("EventID") or decoded.get("EventId") or ""
    if value:
        return value.upper()
    return "HASH-" + hashlib.sha1(url.encode()).hexdigest()[:20]


def extract_match_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        m = MATCH_URL_RE.search(a.get("href", ""))
        if not m:
            continue
        url = urljoin(BASE, m.group(1))
        if url not in out:
            out.append(url)
    return out


def event_meta(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))
    m = re.search(
        r"Kategoria:\s*(.*?)\s+Typ:\s*(Gra\s+(?:pojedyncza|podwójna))\s*;\s*([^|]+?)(?=\s+(?:Grupa\b|Runda:\s*\d+\b|Ćwierćfinał\b|Półfinał\b|Finał\b|Faza\b|lp\b))",
        text,
        re.I,
    )
    if not m:
        return {"kategoria": "", "typ": "", "plec": "", "klucz": ""}
    category, game_type, sex = map(clean, m.groups())
    key = "|".join((fold(category), fold(game_type), fold(sex)))
    return {"kategoria": category, "typ": game_type, "plec": sex, "klucz": key}


def phase_kind(name: str) -> str:
    x = fold(name)
    if x.startswith("grupa") or "faza eliminacyjna" in x:
        return "grupa"
    if x.startswith("runda") or x in {"final", "polfinal", "cwiercfinal"} or "faza finalowa" in x:
        return "puchar"
    return "nieznany"


def score_sets(parts: list[str]) -> list[dict]:
    sets = []
    for part in parts:
        m = SCORE_RE.search(clean(part))
        if m:
            sets.append({"a": int(m.group(1)), "b": int(m.group(2))})
    return sets


def score_winner(parts: list[str]) -> str | None:
    raw = " ".join(clean(x) for x in parts if clean(x))
    # PZT TournamentMatches presents the winner in the left participant column.
    # The retirement marker refers to the opponent even though the portal renders
    # several textual forms (:ret., ret.:, standalone ret.).
    if WO_RE.search(raw) or SPECIAL_LEFT_WIN_RE.search(raw) or RET_RE.search(raw):
        return "a"
    sets = score_sets(parts)
    if not sets:
        return None
    aw = sum(x["a"] > x["b"] for x in sets)
    bw = sum(x["b"] > x["a"] for x in sets)
    if aw == bw:
        return None
    return "a" if aw > bw else "b"


def meaningful_score(parts: list[str]) -> bool:
    raw = " ".join(clean(x) for x in parts if clean(x))
    if not raw or raw == ":":
        return False
    return bool(SCORE_RE.search(raw) or WO_RE.search(raw) or RET_RE.search(raw) or SPECIAL_LEFT_WIN_RE.search(raw))


def parse_event(html: str, source_url: str) -> tuple[dict, list[dict], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    meta = event_meta(html)
    eid = event_id(source_url)
    warnings = []
    matches = []
    seq = 0

    table = None
    for candidate in soup.find_all("table"):
        blob = fold(candidate.get_text(" ", strip=True))
        if "zawodnik" in blob and "set 1" in blob:
            table = candidate
            break
    if table is None:
        return meta, [], ["Nie znaleziono tabeli meczów"]

    phase = ""
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        if len(cells) == 1:
            label = clean(cells[0].get_text(" ", strip=True))
            if label and fold(label) not in {"lp", "zawodnik"}:
                phase = label
            continue
        texts = [clean(c.get_text(" ", strip=True)) for c in cells]
        if len(cells) < 6 or fold(texts[0]) == "lp" or not texts[0].isdigit():
            continue
        left_raw = names_from_cell(cells[1])
        right_raw = names_from_cell(cells[-1])
        if any(fold(x) == "bye" for x in left_raw + right_raw):
            continue
        a = side_from_names(left_raw)
        b = side_from_names(right_raw)
        if not a or not b:
            continue
        score_parts = texts[2:-1]
        if not meaningful_score(score_parts):
            continue
        winner = score_winner(score_parts)
        result_raw = " ".join(x for x in score_parts if x and x != ":")
        seq += 1
        current_phase = phase or "Mecze"
        fp = "|".join((eid, current_phase, texts[0], "/".join(sorted(side_names(a))), "/".join(sorted(side_names(b))), result_raw, str(seq)))
        mid = "pzt-mecz:" + hashlib.sha1(fp.encode()).hexdigest()[:20]
        if not winner:
            warnings.append(f"Nie można ustalić zwycięzcy meczu {mid}")
        matches.append({
            "id": mid,
            "grupa_id": f"pzt:{eid}:{fold(current_phase)}",
            "faza": current_phase,
            "runda": current_phase,
            "typ_fazy": phase_kind(current_phase),
            "strona_a": a,
            "strona_b": b,
            "sety": score_sets(score_parts),
            "wynik": result_raw,
            "walkower": bool(WO_RE.search(result_raw)),
            "zwyciezca": winner,
            "zakonczony": bool(winner),
            "data_zrodlowa": None,
            "kategoria_zrodlowa": ". ".join(x for x in (meta["kategoria"], meta["typ"], meta["plec"]) if x),
            "event_id": eid,
            "event_key": meta["klucz"],
        })

    if not matches:
        warnings.append("Nie znaleziono rozegranych meczów")
    if meta["typ"] and fold(meta["typ"]) == "gra podwojna":
        if any(m["strona_a"]["typ"] != "para" or m["strona_b"]["typ"] != "para" for m in matches):
            warnings.append("Nie udało się jednoznacznie rozpoznać obu par w części meczów deblowych")
    return meta, matches, warnings


def _category_header(value: str) -> dict | None:
    text = clean(value)
    m = re.search(r"Kategoria:\s*(.*?)\.?\s*Typ:\s*(Gra\s+(?:pojedyncza|podwójna))\s*;\s*(.+)$", text, re.I)
    if not m:
        return None
    category, game_type, sex = map(clean, m.groups())
    return {
        "kategoria": category.rstrip("."),
        "typ": game_type,
        "plec": sex,
        "klucz": "|".join((fold(category.rstrip(".")), fold(game_type), fold(sex))),
    }


def parse_winners(html: str) -> dict[str, dict]:
    """Return top two finishers per category key from TournamentTabResults."""
    soup = BeautifulSoup(html, "html.parser")
    strings = [clean(x) for x in soup.stripped_strings if clean(x)]
    out = {}
    current = None
    i = 0
    while i < len(strings):
        header = _category_header(strings[i])
        if header:
            current = {**header, "miejsca": {}}
            out[header["klucz"]] = current
            i += 1
            continue
        if current and strings[i] in {"1", "2"}:
            rank = strings[i]
            need = 2 if fold(current["typ"]) == "gra podwojna" else 1
            names = []
            j = i + 1
            while j < len(strings) and len(names) < need:
                if _category_header(strings[j]) or RANK_RE.match(strings[j]):
                    break
                candidate = strings[j]
                if fold(candidate) not in {"zwyciezcy", "turniej glowny"}:
                    names.append(candidate)
                j += 1
            if names:
                current["miejsca"][rank] = side_from_names(names)
            i = max(j, i + 1)
            continue
        i += 1
    return out


def final_match(matches: list[dict]) -> list[dict]:
    return [m for m in matches if fold(m.get("faza")) == "final" and m.get("zakonczony")]


def verify_final(matches: list[dict], standing: dict | None, warnings: list[str]) -> str | None:
    finals = final_match(matches)
    if len(finals) != 1:
        if len(finals) > 1:
            warnings.append("Więcej niż jeden zakończony finał w jednej konkurencji")
        return None
    final = finals[0]
    if not standing:
        warnings.append("Brak niezależnej klasyfikacji końcowej do potwierdzenia finału")
        return None
    first = standing.get("miejsca", {}).get("1")
    second = standing.get("miejsca", {}).get("2")
    if not first or not second:
        warnings.append("Brak pierwszego lub drugiego miejsca w klasyfikacji końcowej")
        return None
    win = final["strona_" + final["zwyciezca"]]
    lose = final["strona_" + ("b" if final["zwyciezca"] == "a" else "a")]
    if side_names(win) != side_names(first):
        warnings.append("Zwycięzca finału jest sprzeczny z zakładką Zwycięzcy")
        return None
    if side_names(lose) != side_names(second):
        warnings.append("Finalista jest sprzeczny z zakładką Zwycięzcy")
        return None
    return final["id"]


def get(session, url: str) -> str:
    r = session.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0 (compatible; TenisNET/1.0; +https://www.tenis.net.pl/)"}, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    text = r.text
    low = text.casefold()
    if any(x in low for x in ("captcha", "403 forbidden", "access denied", "cloudflare")):
        raise RuntimeError("PZT zablokowało pobranie wyników")
    return text


def fetch(item, session):
    tid = tournament_id(item["url"])
    matches_index = BASE + f"TournamentMatchesPlay.aspx?CategoryID=AIS&Male=&TournamentID={tid}"
    index_html = get(session, matches_index)
    event_urls = extract_match_urls(index_html)
    if not event_urls:
        raise RuntimeError("PZT nie udostępnia stron meczów dla turnieju")

    all_matches = []
    warnings = []
    events = []
    for url in event_urls:
        meta, matches, local = parse_event(get(session, url), url)
        events.append(meta)
        all_matches.extend(matches)
        label = ". ".join(x for x in (meta.get("kategoria"), meta.get("typ"), meta.get("plec")) if x) or event_id(url)
        warnings.extend(f"{label}: {x}" for x in local)

    winners_url = BASE + f"TournamentTabResults.aspx?CategoryID=AIS&Male=&TournamentID={tid}"
    winners = parse_winners(get(session, winners_url))
    unique_keys = [x for x in dict.fromkeys(e.get("klucz") for e in events) if x]

    verified_finals = []
    for key in unique_keys:
        category_matches = [m for m in all_matches if m.get("event_key") == key]
        local = []
        fid = verify_final(category_matches, winners.get(key), local)
        if fid:
            verified_finals.append(fid)
        # A group-only category has no final, so do not call that an extraction error.
        if final_match(category_matches) or any(m["typ_fazy"] == "puchar" for m in category_matches):
            warnings.extend(local)

    if len(unique_keys) > 1:
        warnings.append("Turniej wielokategoriowy — news wymaga kontroli redakcyjnej")
    single_final = verified_finals[0] if len(unique_keys) == 1 and len(verified_finals) == 1 else None
    if len(unique_keys) == 1 and any(m["typ_fazy"] == "puchar" for m in all_matches) and not single_final:
        warnings.append("Brak potwierdzonego pojedynczego finału")
    if len(unique_keys) == 1 and all_matches and all(m["typ_fazy"] == "grupa" for m in all_matches):
        warnings.append("Turniej grupowy bez pojedynczego finału — news wymaga kontroli redakcyjnej")
    if not all_matches:
        warnings.append("Brak wyników meczów")

    labels = []
    for e in events:
        label = ". ".join(x for x in (e.get("kategoria"), e.get("typ"), e.get("plec")) if x)
        if label and label not in labels:
            labels.append(label)

    return {
        "id": "pzt:" + tid,
        "zrodlo": "PZT TOP",
        "url": item["url"],
        "nazwa": str(item.get("nazwa") or ""),
        "kategoria": "; ".join(labels) or str(item.get("kategoria_zrodla") or item.get("kategoria") or ""),
        "data_od": item["data_od"],
        "data_do": item.get("data_do") or item["data_od"],
        "miasto": str(item.get("miasto") or ""),
        "mecze": all_matches,
        "final_id": single_final,
        "gotowy": bool(all_matches) and not warnings,
        "uwagi": sorted(set(warnings)),
    }