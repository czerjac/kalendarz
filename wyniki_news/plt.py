"""PLT API projection: store sporting data only, never raw player profiles."""
import json
from urllib.parse import urlsplit, quote


def data(value, default=None):
    return value.get('data', default) if isinstance(value, dict) else default


def person(p):
    if not isinstance(p, dict) or not p.get('id'):
        return None
    name = ' '.join(str(p.get(k) or '').strip() for k in ('name', 'surname')).strip()
    return {'id': str(p['id']), 'nazwa': name or str(p.get('user_name') or p.get('nick') or '')}


def side(match, which):
    pair = data(match.get(which + 'Pair'))
    if isinstance(pair, dict) and pair.get('id'):
        players = [person(data(pair.get(k))) for k in ('leadPlayer', 'secondPlayer')]
        return {'id': 'para:' + str(pair['id']), 'id_zrodlowe': str(pair['id']),
                'typ': 'para', 'zawodnicy': [p for p in players if p]}
    p = person(data(match.get(which + 'Player')))
    if p:
        return {'id': 'zawodnik:' + p['id'], 'id_zrodlowe': p['id'], 'typ': 'osoba', 'zawodnicy': [p]}
    return None


def parse(payload, item):
    d = data(payload)
    if not isinstance(d, dict) or not d.get('id'):
        raise ValueError('Nieprawidłowa odpowiedź PLT')
    expected = urlsplit(item['url']).path.rstrip('/').split('/')[-2]
    if d.get('slug') != expected:
        raise ValueError('PLT zwróciło inny turniej')
    warnings, matches, seen = [], [], set()
    groups = data(d.get('groups'), [])
    if not isinstance(groups, list):
        raise ValueError('Nieprawidłowa struktura groups')
    for g in groups:
        for raw in data(g.get('resultMatches'), []):
            mid = str(raw.get('id') or '')
            if not mid or mid in seen:
                warnings.append('Brak ID lub powtórzony identyfikator meczu'); continue
            seen.add(mid)
            a, b = side(raw, 'first'), side(raw, 'second')
            try:
                score = json.loads(raw['score']) if isinstance(raw.get('score'), str) else (raw.get('score') or {})
                if not isinstance(score, dict): raise ValueError()
            except (ValueError, TypeError):
                score = {}; warnings.append('Nieczytelny wynik meczu ' + mid)
            sets = []
            for n in range(1, 6):
                x, y = score.get(f'set_{n}_1'), score.get(f'set_{n}_2')
                if x is None and y is None: continue
                if type(x) is not int or type(y) is not int or min(x, y) < 0:
                    warnings.append('Niepełna partia meczu ' + mid); continue
                sets.append({'a': x, 'b': y})
            wid = str(raw.get('winner_id') or '')
            winner = 'a' if a and a['id_zrodlowe'] == wid else 'b' if b and b['id_zrodlowe'] == wid else None
            walkover = raw.get('is_walkover') in (1, True, '1')
            valid_sides = a and b and a['id'] != b['id'] and all(
                len(s['zawodnicy']) == (2 if s['typ'] == 'para' else 1) and all(p['nazwa'] for p in s['zawodnicy']) for s in (a, b))
            done = bool(valid_sides and winner and (sets or walkover))
            if sets and not walkover:
                aw = sum(s['a'] > s['b'] for s in sets)
                bw = sum(s['b'] > s['a'] for s in sets)
                if aw == bw or any(s['a'] == s['b'] for s in sets) or winner != ('a' if aw > bw else 'b'):
                    warnings.append('Wynik nie potwierdza zwycięzcy meczu ' + mid); done = False
            if g.get('type_id') not in (1, 2):
                warnings.append('Nieznany typ fazy ' + str(g.get('type_id')))
            matches.append({'id': mid, 'grupa_id': str(g.get('id')), 'faza': str(g.get('name') or ''),
                            'typ_fazy': 'grupa' if g.get('type_id') == 1 else 'puchar' if g.get('type_id') == 2 else 'nieznany',
                            'strona_a': a, 'strona_b': b, 'sety': sets,
                            'wynik': ', '.join(f"{s['a']}:{s['b']}" for s in sets) + (' (walkower)' if walkover else ''),
                            'walkower': walkover, 'zwyciezca': winner, 'zakonczony': done,
                            'data_zrodlowa': raw.get('date_match')})
    finals = [m for m in matches if m['typ_fazy'] == 'puchar' and m['faza'].strip().casefold() in ('finał', 'final')]
    knockout = any(m['typ_fazy'] == 'puchar' for m in matches) or bool(d.get('is_cup_phase'))
    if knockout and (len(finals) != 1 or not finals[0]['zakonczony']): warnings.append('Brak potwierdzonego pojedynczego finału')
    if not knockout and len(groups) != 1: warnings.append('Niepotwierdzony format końcowy')
    if not matches or any(not m['zakonczony'] for m in matches): warnings.append('Brak części rozegranych meczów lub wyników')
    # Do not infer winners from numeric table order; no fabricated final in round-robin.
    return {'id': 'plt:' + str(d['id']), 'zrodlo': 'PLT', 'url': item['url'],
            'nazwa': str(d.get('title') or item['nazwa']), 'kategoria': str(item.get('kategoria_zrodla') or item.get('kategoria') or ''),
            'data_od': item['data_od'], 'data_do': item.get('data_do') or item['data_od'],
            'miasto': str(item.get('miasto') or d.get('location') or ''),
            'mecze': matches, 'final_id': finals[0]['id'] if len(finals) == 1 else None,
            'gotowy': bool(matches) and not warnings, 'uwagi': sorted(set(warnings))}


def fetch(item, session):
    u = urlsplit(item['url'])
    if u.scheme != 'https' or u.hostname not in ('polskaligatenisa.pl', 'www.polskaligatenisa.pl'):
        raise ValueError('Nieprawidłowy adres PLT')
    parts = u.path.rstrip('/').split('/')
    if len(parts) < 4 or parts[-1] != 'wyniki': raise ValueError('Brak adresu /wyniki')
    url = 'https://api.polskaligatenisa.pl/api/V1/rounds/' + quote(parts[-2], safe='-')
    r = session.get(url, params={'include': 'groups.resultMatches.firstPlayer,groups.resultMatches.secondPlayer,doublePairs'}, timeout=40)
    r.raise_for_status()
    return parse(r.json(), item)
