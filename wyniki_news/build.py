"""Produce cumulative sports-only results and editorial feed; no WordPress writes."""
import argparse
import hashlib
import html
import json
import os
import time
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


def label(side):
    return ' / '.join(p['nazwa'] for p in side['zawodnicy']) if side else 'Nieustalony uczestnik'


def article(t):
    esc = lambda x: html.escape(str(x), quote=True)
    finished = [m for m in t['mecze'] if m['zakonczony']]
    final = next((m for m in finished if m['id'] == t['final_id']), None)
    intro = f"Turniej {esc(t['nazwa'])} ({esc(t['data_od'])}"
    if t['data_do'] != t['data_od']:
        intro += ' – ' + esc(t['data_do'])
    intro += f"){(' w miejscowości ' + esc(t['miasto'])) if t['miasto'] else ''}."
    if final:
        intro += f" Zwycięstwo w finale: {esc(label(final['strona_' + final['zwyciezca']]))}. Drugie miejsce: {esc(label(final['strona_' + ('b' if final['zwyciezca']=='a' else 'a')]))}."
    parts = ['<p>' + intro + '</p>', '<p>Kategoria źródłowa: ' + esc(t['kategoria']) + '.</p>']
    if not t['gotowy']:
        parts.append('<p><strong>Wyniki wymagają sprawdzenia; zestawienie może być niepełne.</strong></p>')
    for gid in dict.fromkeys(m['grupa_id'] for m in t['mecze']):
        group = [m for m in t['mecze'] if m['grupa_id'] == gid]
        category = group[0].get('kategoria_zrodlowa') or ''
        if category and category != t['kategoria']:
            parts.append('<h2>' + esc(category) + '</h2>')
            heading = 'h3'
        else:
            heading = 'h2'
        parts += [f'<{heading}>' + esc(group[0]['faza']) + f'</{heading}>', '<figure class="wp-block-table"><table><thead><tr><th>Zawodnik / para A</th><th>Zawodnik / para B</th><th>Wynik A:B</th></tr></thead><tbody>']
        for m in group:
            result = m['wynik'] if m['zakonczony'] else 'Brak potwierdzonego wyniku'
            parts.append('<tr><td>' + esc(label(m['strona_a'])) + '</td><td>' + esc(label(m['strona_b'])) + '</td><td>' + esc(result) + '</td></tr>')
        parts.append('</tbody></table></figure>')
    parts.append('<p>Źródło: <a href="' + esc(t['url']) + '">' + esc(t['zrodlo']) + ' — wyniki turnieju</a>.</p>')
    title = t['nazwa'] + ' — wyniki (' + t['data_od'] + ')'
    body = '\n'.join(parts)
    return {'id': t['id'], 'title': title, 'content': body, 'source_url': t['url'], 'source': t['zrodlo'],
            'date_start': t['data_od'], 'date_end': t['data_do'], 'ready': t['gotowy'], 'issues': t['uwagi'],
            'fingerprint': hashlib.sha256((title + '\n' + body).encode()).hexdigest()}


def discover():
    # Read-only union with current calendar keeps future events after they disappear.
    merged = {}
    paths = sorted((ROOT / 'data/archiwum').glob('*/turnieje.json')) + [ROOT / 'data/turnieje.json']
    for path in paths:
        for item in load(path, {}).get('turnieje', []):
            if item.get('url'):
                merged[item['url']] = {k: item[k] for k in ('url', 'zrodlo', 'nazwa', 'kategoria', 'kategoria_zrodla', 'miasto', 'data_od', 'data_do') if k in item}
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
    posts = [article(t) for t in state['results'].values()]
    posts.sort(key=lambda x: (x['date_end'], x['id']))
    # Weekly window is Friday–Monday; delayed results use backfill/manual import or retry queue.
    monday = today - timedelta(days=(today.weekday() - 0) % 7)
    weekend_start = monday - timedelta(days=3)
    feed = {'schema_version': 1, 'generated_at': now.isoformat(), 'run_date': today.isoformat(),
            'cutoff_exclusive': CUTOFF.isoformat(), 'weekend_start': weekend_start.isoformat(),
            'weekend_end': monday.isoformat(), 'supported_sources': list(ADAPTERS), 'posts': posts}
    save(OUT / 'stan.json', state)
    save(OUT / 'feed.json', feed)
    report = {'generated_at': now.isoformat(), 'attempted': len(jobs), 'errors': errors,
              'ready': sum(x['ready'] for x in posts), 'needs_review': sum(not x['ready'] for x in posts),
              'awaiting_adapter': dict(Counter(x['zrodlo'] for x in pending))}
    for source, key in (('PLT', 'plt'), ('Cuply', 'cuply'), ('Kluby.org', 'kluby'), ('PZT TOP', 'pzt')):
        report[f'remaining_unfetched_{key}'] = sum(
            x['url'] not in state['attempts'] for x in candidates if x.get('zrodlo') == source
        )
    save(OUT / 'raport.json', report)
    if errors:
        print('Some source requests failed; last good results preserved.', flush=True)


if __name__ == '__main__':
    main()
