from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

CALENDAR_FILE = Path("data/turnieje.json")
CACHE_FILE = Path("data/miasta_wojewodztwa.json")
UNRESOLVED_FILE = Path("data/nierozpoznane_lokalizacje.json")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "tenis.net.pl-kalendarz/1.0 (https://github.com/czerjac/kalendarz)"
AMBIGUOUS_KEYS = {"kamien"}

WOJEWODZTWA = {
    "dolnoslaskie": "dolnośląskie",
    "kujawsko-pomorskie": "kujawsko-pomorskie",
    "lubelskie": "lubelskie",
    "lubuskie": "lubuskie",
    "lodzkie": "łódzkie",
    "malopolskie": "małopolskie",
    "mazowieckie": "mazowieckie",
    "opolskie": "opolskie",
    "podkarpackie": "podkarpackie",
    "podlaskie": "podlaskie",
    "pomorskie": "pomorskie",
    "slaskie": "śląskie",
    "swietokrzyskie": "świętokrzyskie",
    "warminsko-mazurskie": "warmińsko-mazurskie",
    "wielkopolskie": "wielkopolskie",
    "zachodniopomorskie": "zachodniopomorskie",
}

MANUAL_OVERRIDES = {
    "warszawa": "mazowieckie", "krakow": "małopolskie", "lodz": "łódzkie",
    "wroclaw": "dolnośląskie", "poznan": "wielkopolskie", "gdansk": "pomorskie",
    "gdynia": "pomorskie", "sopot": "pomorskie", "szczecin": "zachodniopomorskie",
    "bialystok": "podlaskie", "lublin": "lubelskie", "rzeszow": "podkarpackie",
    "kielce": "świętokrzyskie", "opole": "opolskie", "zielona gora": "lubuskie",
    "gorzow wielkopolski": "lubuskie", "bydgoszcz": "kujawsko-pomorskie",
    "torun": "kujawsko-pomorskie", "olsztyn": "warmińsko-mazurskie",
    "koszalin": "zachodniopomorskie", "kolobrzeg": "zachodniopomorskie",
    "gryfino": "zachodniopomorskie", "stargard": "zachodniopomorskie",
    "doluje": "zachodniopomorskie", "mierzyn": "zachodniopomorskie",
    "myszkow": "śląskie", "katowice": "śląskie", "chorzow": "śląskie",
    "biala podlaska": "lubelskie", "minsk mazowiecki": "mazowieckie",
    "zyrardow": "mazowieckie", "ostroleka": "mazowieckie", "plock": "mazowieckie",
    "lomza": "podlaskie", "pisz": "warmińsko-mazurskie", "reda": "pomorskie",
    "rumia": "pomorskie", "wejherowo": "pomorskie", "inowroclaw": "kujawsko-pomorskie",
    "wloclawek": "kujawsko-pomorskie", "oborniki": "wielkopolskie",
    "legnica": "dolnośląskie", "radom": "mazowieckie", "zamosc": "lubelskie",
    "stalowa wola": "podkarpackie", "olesno": "opolskie",
    "barlinek": "zachodniopomorskie", "chelmek k oswiecimia": "małopolskie",
    "konin": "wielkopolskie", "krosno": "podkarpackie", "olesnica": "dolnośląskie",
    "piaseczno": "mazowieckie", "zawiercie": "śląskie", "leczna": "lubelskie",
}


def ascii_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("ł", "l")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def normalize_state(value: str) -> str:
    key = ascii_key(value).replace("wojewodztwo ", "").replace(" voivodeship", "").replace(" ", "-")
    return WOJEWODZTWA.get(key, "")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def query_one(name: str) -> tuple[str, list[dict]]:
    response = requests.get(
        NOMINATIM_URL,
        params={"q": f"{name}, Polska", "format": "jsonv2", "addressdetails": 1, "countrycodes": "pl", "limit": 5},
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pl"},
        timeout=20,
    )
    response.raise_for_status()
    states, evidence = [], []
    for item in response.json():
        state = normalize_state((item.get("address") or {}).get("state", ""))
        if state:
            states.append(state)
        evidence.append({"display_name": item.get("display_name", ""), "wojewodztwo": state})
    unique_states = sorted(set(states))
    return (unique_states[0] if len(unique_states) == 1 else ""), evidence


def resolve_city(city: str, cache: dict) -> tuple[str, dict]:
    original = " ".join((city or "").split())
    key = ascii_key(original)
    if not key:
        return "", {"powod": "brak_miasta"}

    # Nazwa "Kamień" występuje w wielu województwach. Nie ufamy ani geokoderowi,
    # ani staremu cache — właściwe województwo ma podać strona konkretnego turnieju.
    if key in AMBIGUOUS_KEYS:
        return "", {"powod": "niejednoznaczna_nazwa_miejscowosci"}

    if key in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[key], {"metoda": "reczna_regula"}

    cached = cache.get(key)
    if isinstance(cached, dict) and cached.get("wojewodztwo"):
        return cached["wojewodztwo"], {"metoda": "cache"}

    parts = [part.strip() for part in re.split(r"\s*/\s*", original) if part.strip()]
    if len(parts) > 1:
        found, evidences = [], []
        for part in parts:
            manual = MANUAL_OVERRIDES.get(ascii_key(part), "")
            if manual:
                found.append(manual)
                evidences.append({"czesc": part, "wojewodztwo": manual, "metoda": "reczna_regula"})
                continue
            woj, ev = query_one(part)
            time.sleep(1.05)
            if woj:
                found.append(woj)
            evidences.append({"czesc": part, "wojewodztwo": woj, "wyniki": ev})
        if found and len(set(found)) == 1:
            return found[0], {"metoda": "geokoder_wieloczlonowy", "dowody": evidences}
        return "", {"powod": "niejednoznaczna_lokalizacja_wieloczlonowa", "dowody": evidences}

    try:
        woj, evidence = query_one(original)
        time.sleep(1.05)
        if woj:
            return woj, {"metoda": "nominatim", "dowody": evidence}
        return "", {"powod": "brak_jednoznacznego_wojewodztwa", "dowody": evidence}
    except Exception as exc:
        return "", {"powod": "blad_geokodera", "blad": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    calendar = load_json(CALENDAR_FILE, {})
    tournaments = calendar.get("turnieje", [])
    if not tournaments:
        raise RuntimeError("Brak turniejów w data/turnieje.json")

    cache_data = load_json(CACHE_FILE, {"miasta": {}})
    cache = cache_data.setdefault("miasta", {})
    for key in AMBIGUOUS_KEYS:
        cache.pop(key, None)

    unresolved_by_city: dict[str, dict] = {}
    unique_cities = sorted({" ".join((item.get("miasto") or "").split()) for item in tournaments if item.get("miasto")})
    resolved: dict[str, str] = {}

    for city in unique_cities:
        key = ascii_key(city)
        woj, details = resolve_city(city, cache)
        if woj:
            resolved[city] = woj
            cache[key] = {
                "miasto": city, "wojewodztwo": woj, "metoda": details.get("metoda", ""),
                "aktualizacja_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        else:
            unresolved_by_city[city] = {"miasto": city, **details}

    missing_count = 0
    for item in tournaments:
        city = " ".join((item.get("miasto") or "").split())
        item["wojewodztwo"] = resolved.get(city, "")
        if not item["wojewodztwo"]:
            missing_count += 1

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    calendar["regiony_aktualizacja_utc"] = now
    calendar["liczba_turniejow_bez_wojewodztwa"] = missing_count
    CALENDAR_FILE.write_text(json.dumps(calendar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache_data["aktualizacja_utc"] = now
    cache_data["liczba_miast"] = len(cache)
    CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    unresolved = {"aktualizacja_utc": now, "liczba_nierozpoznanych_miast": len(unresolved_by_city), "miasta": list(unresolved_by_city.values())}
    UNRESOLVED_FILE.write_text(json.dumps(unresolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Województwa: rozpoznano {len(resolved)}/{len(unique_cities)} miejscowości")
    print(f"Turnieje bez województwa: {missing_count}")
    if unresolved_by_city:
        print("Do ręcznej weryfikacji:", ", ".join(unresolved_by_city))


if __name__ == "__main__":
    main()
