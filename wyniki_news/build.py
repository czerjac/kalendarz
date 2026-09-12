"""Produce cumulative sports-only results and editorial feed; no WordPress writes."""
import argparse
import hashlib
import html
import json
import os
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from . import cuply, kluby, plt, pzt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'wyniki_news'
CUTOFF = date(2026, 7, 1)  # User requested strictly AFTER July 1.
ADAPTERS = {
    'PLT': plt.fetch,
    'Cuply': cuply.fetch,
    'Kluby.org': kluby.fetch,
    'PZT TOP': pzt.fetch,
}

MONTHS_PL = {
    1: 'stycznia', 2: 'lutego', 3: 'marca', 4: 'kwietnia', 5: 'maja', 6: 'czerwca',
    7: 'lipca', 8: 'sierpnia', 9: 'września', 10: 'października', 11: 'listopada', 12: 'grudnia',
}


def load(path, default):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    os.replace(temp, path)


def eligible(item, today):
    try:
        end = date.fromisoformat(item.get('data_do') or item['data_od'])
        return CUTOFF < end < today
    except (ValueError, KeyError, TypeError):
        return False


def label(side, separator=', '):
    return separator.join(p['nazwa'] for p in side['zawodnicy']) if side else 'Nieustalony uczestnik'


def fold_text(value):
    text = str(value or '').casefold().replace('ł', 'l')
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def date_phrase(start, end):
    try:
        a = date.fromisoformat(start)
        b = date.fromisoformat(end or start)
    except (TypeError, ValueError):
        return str(start), 'W dniu'
    if a == b:
        return f'{a.day} {MONTHS_PL[a.month]} {a.year}', 'W dniu'
    if a.year == b.year and a.month == b.month:
        return f'{a.day}–{b.day} {MONTHS_PL[a.month]} {a.year}', 'W dniach'
    if a.year == b.year:
        return f'{a.day} {MONTHS_PL[a.month]} – {b.day} {MONTHS_PL[b.month]} {a.year}', 'W dniach'
    return f'{a.day} {MONTHS_PL[a.month]} {a.year} – {b.day} {MONTHS_PL[b.month]} {b.year}', 'W dniach'


def suggested_tags(t, meta):
    tags = []
    source_tag = {
        'PZT TOP': 'Tenis Open Polska PZT',
        'PLT': 'Polska Liga Tenisa',
        'Cuply': 'Cuply',
    }.get(t.get('zrodlo'))
    if source_tag:
        tags.append(source_tag)

    folded = fold_text(meta.get('cykl') or '')
    for needle, tag in (
        ('grand prix mazowsza', 'Grand Prix Mazowsza'),
        ('grand prix wybrzeza', 'Grand Prix Wybrzeża'),
        ('grand prix podlasia i mazur', 'Grand Prix Podlasia i Mazur'),
    ):
        if needle in folded and tag not in tags:
            tags.append(tag)
    return tags


def singles_gender(category):
    value = fold_text(category)
    if any(token in value for token in ('kobiet', 'panie', 'women', 'damsk')):
        return 'female'
    if any(token in value for token in ('mezczy', 'panowie', 'men', 'mesk')):
        return 'male'
    return None


def article(t, meta=None):
    meta = meta or {}
    esc = lambda x: html.escape(str(x), quote=True)
    finished = [m for m in t['mecze'] if m['zakonczony']]
    final = next((m for m in finished if m['id'] == t['final_id']), None)

    category = str(meta.get('kategorie') or meta.get('kategoria_zrodla') or t.get('kategoria') or '')
    cycle = str(meta.get('cykl') or '')
    venue = str(meta.get('miejsce') or '')
    city = str(meta.get('miasto') or t.get('miasto') or '')
    date_text, date_intro = date_phrase(t['data_od'], t['data_do'])

    if venue and city:
        location = f' na obiekcie {esc(venue)} ({esc(city)})'
    elif venue:
        location = f' na obiekcie {esc(venue)}'
    elif city:
        location = f' w miejscowości {esc(city)}'
    else:
        location = ''

    intro = f'{date_intro} {esc(date_text)}{location} rozegrano turniej {esc(t["nazwa"])}'
    if category:
        intro += f' w kategorii {esc(category)}'
    intro += '.'
    if cycle and fold_text(cycle) not in {'brak', 'none'}:
        intro += f' Zawody były częścią cyklu {esc(cycle)}.'

    winner = loser = None
    if final and final.get('zwyciezca') in {'a', 'b'}:
        winner_key = final['zwyciezca']
        loser_key = 'b' if winner_key == 'a' else 'a'
        winner = final['strona_' + winner_key]
        loser = final['strona_' + loser_key]
        result = esc(final.get('wynik') or '')
        winner_label = esc(label(winner))
        loser_label = esc(label(loser))
        if len(winner.get('zawodnicy', [])) == 2 and len(loser.get('zawodnicy', [])) == 2:
            intro += f' Zwyciężyła para {winner_label}, która w finale okazała się lepsza od pary {loser_label}'
            if result:
                intro += f' {result}'
            intro += '.'
        else:
            gender = singles_gender(category or t.get('kategoria', ''))
            if gender == 'female':
                intro += f' W finale {winner_label} pokonała {loser_label}'
            elif gender == 'male':
                intro += f' W finale {winner_label} pokonał {loser_label}'
            else:
                intro += f' Finał: {winner_label} – {loser_label}'
            if result:
                intro += f' {result}'
            intro += '.'
    intro += ' Poniżej szczegółowe wyniki.'

    parts = ['<p>' + intro + '</p>']
    if not t['gotowy']:
        parts.append('<p><strong>Wyniki wymagają sprawdzenia; zestawienie może być niepełne.</strong></p>')

    shown_categories = set()
    for gid in dict.fromkeys(m['grupa_id'] for m in t['mecze']):
        group = [m for m in t['mecze'] if m['grupa_id'] == gid]
        source_category = group[0].get('kategoria_zrodlowa') or ''
        if source_category and source_category != t.get('kategoria') and source_category not in shown_categories:
            parts.append('<h2>' + esc(source_category) + '</h2>')
            shown_categories.add(source_category)
            heading = 'h3'
        else:
            heading = 'h3' if source_category and source_category in shown_categories else 'h2'
        parts.append(f'<{heading}>' + esc(group[0]['faza']) + f'</{heading}>')
        lines = []
        for match in group:
            result = match['wynik'] if match['zakonczony'] else 'Brak potwierdzonego wyniku'
            lines.append(
                esc(label(match['strona_a'])) + ' – ' + esc(label(match['strona_b'])) +
                ' <strong>' + esc(result) + '</strong>'
            )
        parts.append('<p>' + '<br>\n'.join(lines) + '</p>')

    parts.append('<p>Źródło: <a href="' + esc(t['url']) + '">' + esc(t['zrodlo']) + ' — wyniki turnieju</a>.</p>')

    if final and winner:
        prefix = (city + ': ') if city else ''
        verb = 'triumfują' if len(winner.get('zawodnicy', [])) == 2 else 'triumfuje'
        title = prefix + label(winner) + f' {verb} w turnieju ' + t['nazwa']
    else:
        title = t['nazwa'] + ' — wyniki (' + t['data_od'] + ')'

    body = '\n'.join(parts)
    return {
        'id': t['id'],
        'title': title,
        'content': body,
        'source_url': t['url'],
        'source': t['zrodlo'],
        'date_start': t['data_od'],
        'date_end': t['data_do'],
        'ready': t['gotowy'],
        'issues': t['uwagi'],
        'voivodeship': str(meta.get('wojewodztwo') or ''),
        'cycle': cycle,
        'tags': suggested_tags(t, meta),
        'fingerprint': hashlib.sha256((title + '\n' + body).encode()).hexdigest(),
    }


def discover():
    # Read-only union with current calendar keeps future events after they disappear.
    merged = {}
    paths = sorted((ROOT / 'data/archiwum').glob('*/turnieje.json')) + [ROOT / 'data/turnieje.json']
    for path in paths:
        for item in load(path, {}).get('turnieje', []):
            if item.get('url'):
                merged[item['url']] = {
                    k: item[k]
                    for k in (
                        'url', 'zrodlo', 'nazwa', 'kategoria', 'kategoria_zrodla', 'kategorie',
                        'miasto', 'miejsce', 'wojewodztwo', 'cykl', 'rodzaje_gry', 'data_od', 'data_do'
                    )
                    if k in item
                }
    return merged


def main():
    import requests
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--today', type=date.fromisoformat)
    ap.add_argument('--backfill', action='store_true', help='Ręcznie odśwież całe archiwum po 1 lipca; domyślnie tylko ostatnie 7 dni')
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    today = args.today or datetime.now(ZoneInfo('Europe/Warsaw')).date()
    state = load(OUT / 'stan.json', {'known': {}, 'attempts': {}, 'results': {}})
    state['known'].update(discover())
    candidates = [x for x in state['known'].values() if eligible(x, today)]
    pending = [x for x in candidates if x.get('zrodlo') not in ADAPTERS]
    jobs = []
    for x in candidates:
        if x.get('zrodlo') not in ADAPTERS:
            continue
        # Weekly snapshot only; older events require an explicit manual backfill.
        age = (today - date.fromisoformat(x.get('data_do') or x['data_od'])).days
        if args.backfill or age <= 7:
            jobs.append(x)
    jobs.sort(key=lambda x: (state['attempts'].get(x['url'], {}).get('date', ''), x['data_od'], x.get('zrodlo', '')))
    if args.limit:
        jobs = jobs[:args.limit]
    errors = []
    with requests.Session() as session:
        for index, item in enumerate(jobs):
            source = item.get('zrodlo')
            try:
                result = ADAPTERS[source](item, session)
                previous = state['results'].get(result['id'])
                # Preserve last good data on partial/regressed response; disable automatic publishing.
                if previous and (len(result['mecze']) < len(previous['mecze']) or (previous['gotowy'] and not result['gotowy'])):
                    previous['gotowy'] = False
                    previous['uwagi'] = sorted(set(previous['uwagi'] + ['Nowszy odczyt jest niepełny — zachowano poprzednie wyniki']))
                else:
                    state['results'][result['id']] = result
                state['attempts'][item['url']] = {'date': today.isoformat(), 'ready': result['gotowy']}
            except Exception as exc:
                errors.append({'url': item['url'], 'source': source, 'error': type(exc).__name__})
                state['attempts'][item['url']] = {'date': today.isoformat(), 'ready': False}
            print(f"{source or 'SOURCE'} {index+1}/{len(jobs)}", flush=True)
            save(OUT / 'stan.json', state)
            time.sleep(0.25)

    posts = [article(t, state['known'].get(t.get('url', ''), {})) for t in state['results'].values()]
    posts.sort(key=lambda x: (x['date_end'], x['id']))
    # Weekly window is Friday–Monday; delayed results use backfill/manual import or retry queue.
    monday = today - timedelta(days=(today.weekday() - 0) % 7)
    weekend_start = monday - timedelta(days=3)
    feed = {
        'schema_version': 1,
        'generated_at': now.isoformat(),
        'run_date': today.isoformat(),
        'cutoff_exclusive': CUTOFF.isoformat(),
        'weekend_start': weekend_start.isoformat(),
        'weekend_end': monday.isoformat(),
        'supported_sources': list(ADAPTERS),
        'posts': posts,
    }
    save(OUT / 'stan.json', state)
    save(OUT / 'feed.json', feed)
    report = {
        'generated_at': now.isoformat(),
        'attempted': len(jobs),
        'errors': errors,
        'ready': sum(x['ready'] for x in posts),
        'needs_review': sum(not x['ready'] for x in posts),
        'awaiting_adapter': dict(Counter(x['zrodlo'] for x in pending)),
    }
    for source, key in (('PLT', 'plt'), ('Cuply', 'cuply'), ('Kluby.org', 'kluby'), ('PZT TOP', 'pzt')):
        report[f'remaining_unfetched_{key}'] = sum(
            x['url'] not in state['attempts'] for x in candidates if x.get('zrodlo') == source
        )
    save(OUT / 'raport.json', report)
    if errors:
        print('Some source requests failed; last good results preserved.', flush=True)


if __name__ == '__main__':
    main()
