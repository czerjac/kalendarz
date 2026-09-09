from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path('data/diagnostyka_wynikow_2026.json')
OUT = Path('data/diagnostyka_wynikow_2026_summary.json')

KEYWORDS = re.compile(r'(wynik|grup|drab|play.?off|puchar|mecz|fina|round|stage|draw|match|bracket|api|ajax)', re.I)


def main():
    data = json.loads(SRC.read_text(encoding='utf-8'))
    rows = []
    for s in data.get('probki', []):
        text = s.get('body_text', '')
        elements = []
        for e in s.get('elements', []):
            blob = ' '.join(str(e.get(k, '')) for k in ('text','href','onclick','id','name'))
            if KEYWORDS.search(blob):
                elements.append(e)
        network = []
        for n in s.get('network', []):
            blob = ' '.join(str(n.get(k, '')) for k in ('url','content_type','resource_type'))
            if KEYWORDS.search(blob) or n.get('resource_type') in {'xhr','fetch'}:
                network.append(n)
        rows.append({
            'label': s.get('label'),
            'url': s.get('url'),
            'final_url': s.get('final_url'),
            'error': s.get('error'),
            'meta': s.get('meta', {}),
            'ma_grupy': bool(re.search(r'\bgrup', text, re.I)),
            'ma_drabinke': bool(re.search(r'drabink', text, re.I)),
            'ma_faze_pucharowa': bool(re.search(r'faza puchar|pucharow|play.?off', text, re.I)),
            'ma_wyniki': bool(re.search(r'wynik', text, re.I)),
            'elementy_istotne': elements[:80],
            'network_istotny': network[:80],
            'popups': s.get('popups', [])[:20],
            'tekst_poczatek': text[:5000],
        })
    OUT.write_text(json.dumps({'liczba_probek': len(rows), 'probki': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Zapisano', OUT)

if __name__ == '__main__':
    main()
