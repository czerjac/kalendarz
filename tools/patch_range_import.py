from pathlib import Path

# Patch targeted date-range backfill in the generator.
build = Path('wyniki_news/build.py')
s = build.read_text(encoding='utf-8')

anchor = """def main():
    import requests
"""
helper = """def overlaps_date_range(item, start, end):
    if start is None or end is None:
        return True
    try:
        item_start = date.fromisoformat(item.get('data_od') or item.get('data_do'))
        item_end = date.fromisoformat(item.get('data_do') or item.get('data_od'))
    except (TypeError, ValueError):
        return False
    return item_end >= start and item_start <= end


def main():
    import requests
"""
assert anchor in s
s = s.replace(anchor, helper, 1)

old_args = """    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--today', type=date.fromisoformat)
    ap.add_argument('--backfill', action='store_true', help='Ręcznie odśwież całe archiwum po 1 lipca; domyślnie tylko ostatnie 7 dni')
    args = ap.parse_args()
"""
new_args = """    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--today', type=date.fromisoformat)
    ap.add_argument('--backfill', action='store_true', help='Ręcznie odśwież całe archiwum po 1 lipca; domyślnie tylko ostatnie 7 dni')
    ap.add_argument('--date-from', dest='date_from', type=date.fromisoformat, help='Początek celowanego zakresu YYYY-MM-DD')
    ap.add_argument('--date-to', dest='date_to', type=date.fromisoformat, help='Koniec celowanego zakresu YYYY-MM-DD')
    args = ap.parse_args()
    if (args.date_from is None) != (args.date_to is None):
        ap.error('--date-from i --date-to muszą być podane razem')
    if args.date_from and args.date_from > args.date_to:
        ap.error('--date-from nie może być późniejsza niż --date-to')
"""
assert old_args in s
s = s.replace(old_args, new_args, 1)

old_candidates = """    candidates = [x for x in state['known'].values() if eligible(x, today)]
    pending = [x for x in candidates if x.get('zrodlo') not in ADAPTERS]
"""
new_candidates = """    candidates = [
        x for x in state['known'].values()
        if eligible(x, today) and overlaps_date_range(x, args.date_from, args.date_to)
    ]
    pending = [x for x in candidates if x.get('zrodlo') not in ADAPTERS]
"""
assert old_candidates in s
s = s.replace(old_candidates, new_candidates, 1)

old_age = """        if args.backfill or age <= 7:
            jobs.append(x)
"""
new_age = """        if args.backfill or args.date_from is not None or age <= 7:
            jobs.append(x)
"""
assert old_age in s
s = s.replace(old_age, new_age, 1)
build.write_text(s, encoding='utf-8')

# Patch WordPress importer with a date-range form and range-aware import.
core = Path('wordpress/tenis-net-wyniki/tenis-net-wyniki-core.inc')
p = core.read_text(encoding='utf-8')
p = p.replace(' * Version: 0.3.0', ' * Version: 0.4.0', 1)
p = p.replace(
    "        add_action('admin_post_tnw_import', array(__CLASS__, 'manual'));\n",
    "        add_action('admin_post_tnw_import', array(__CLASS__, 'manual'));\n        add_action('admin_post_tnw_import_range', array(__CLASS__, 'manual_range'));\n",
    1,
)
old_ui = """        echo '<form method=\"post\" action=\"' . esc_url(admin_url('admin-post.php')) . '\"><input type=\"hidden\" name=\"action\" value=\"tnw_import\">'; wp_nonce_field('tnw_import'); submit_button('Importuj kolejne 10 turniejów od lipca', 'secondary'); echo '</form>';
        echo '<h2>Ostatni przebieg</h2><pre>' . esc_html(get_option('tnw_last_report', 'Jeszcze nie uruchomiono.')) . '</pre></div>';
"""
new_ui = """        echo '<form method=\"post\" action=\"' . esc_url(admin_url('admin-post.php')) . '\"><input type=\"hidden\" name=\"action\" value=\"tnw_import\">'; wp_nonce_field('tnw_import'); submit_button('Importuj kolejne 10 turniejów od lipca', 'secondary'); echo '</form>';
        echo '<h3>Import z wybranego zakresu dat</h3><p>Wybierz maksymalnie 14 kolejnych dni. Import obejmie wyłącznie turnieje, których termin choć częściowo pokrywa się z zakresem. Jedno kliknięcie obsłuży do 50 nowych lub zmienionych wpisów; ponowienie nie tworzy duplikatów.</p>';
        echo '<form method=\"post\" action=\"' . esc_url(admin_url('admin-post.php')) . '\"><input type=\"hidden\" name=\"action\" value=\"tnw_import_range\">'; wp_nonce_field('tnw_import_range');
        echo '<p><label>Od: <input type=\"date\" name=\"date_from\" required></label> &nbsp; <label>Do: <input type=\"date\" name=\"date_to\" required></label></p>';
        submit_button('Importuj turnieje z zakresu', 'secondary'); echo '</form>';
        echo '<h2>Ostatni przebieg</h2><pre>' . esc_html(get_option('tnw_last_report', 'Jeszcze nie uruchomiono.')) . '</pre></div>';
"""
assert old_ui in p
p = p.replace(old_ui, new_ui, 1)

old_manual = """    public static function manual() {
        self::guard(); check_admin_referer('tnw_import'); self::import(true);
        wp_safe_redirect(admin_url('tools.php?page=tnw')); exit;
    }

    public static function scheduled() {
"""
new_manual = """    public static function manual() {
        self::guard(); check_admin_referer('tnw_import'); self::import(true);
        wp_safe_redirect(admin_url('tools.php?page=tnw')); exit;
    }

    public static function manual_range() {
        self::guard(); check_admin_referer('tnw_import_range');
        $from = sanitize_text_field($_POST['date_from'] ?? '');
        $to = sanitize_text_field($_POST['date_to'] ?? '');
        $tz = new DateTimeZone('Europe/Warsaw');
        $from_dt = DateTimeImmutable::createFromFormat('!Y-m-d', $from, $tz);
        $to_dt = DateTimeImmutable::createFromFormat('!Y-m-d', $to, $tz);
        if (!$from_dt || !$to_dt || $from_dt->format('Y-m-d') !== $from || $to_dt->format('Y-m-d') !== $to) {
            wp_die('Podaj poprawny zakres dat.');
        }
        if ($from_dt > $to_dt) { wp_die('Data początkowa nie może być późniejsza niż końcowa.'); }
        if (($to_dt->getTimestamp() - $from_dt->getTimestamp()) > 13 * 86400) { wp_die('Zakres może obejmować maksymalnie 14 dni.'); }
        self::import(true, $from, $to);
        wp_safe_redirect(admin_url('tools.php?page=tnw')); exit;
    }

    public static function scheduled() {
"""
assert old_manual in p
p = p.replace(old_manual, new_manual, 1)

p = p.replace('    public static function import($manual) {', '    public static function import($manual, $range_from = null, $range_to = null) {', 1)

old_filter = """                if (!$manual) {
                    $end = $entry['date_end'];
                    // Exactly the previous seven calendar days, Tuesday through Monday.
                    if ($end < $tuesday->modify('-7 days')->format('Y-m-d') || $end >= $tuesday->format('Y-m-d')) { continue; }
                }
                $slug = 'tnw-' . str_replace(':', '-', $entry['id']);
"""
new_filter = """                if (!$manual) {
                    $end = $entry['date_end'];
                    // Exactly the previous seven calendar days, Tuesday through Monday.
                    if ($end < $tuesday->modify('-7 days')->format('Y-m-d') || $end >= $tuesday->format('Y-m-d')) { continue; }
                }
                if ($manual && $range_from !== null && $range_to !== null) {
                    $start = $entry['date_start'] ?? $entry['date_end'];
                    $end = $entry['date_end'] ?? $entry['date_start'];
                    if ($end < $range_from || $start > $range_to) { continue; }
                }
                $slug = 'tnw-' . str_replace(':', '-', $entry['id']);
"""
assert old_filter in p
p = p.replace(old_filter, new_filter, 1)

old_limit = """                if ($manual && $done >= 10) { $remaining++; continue; }
"""
new_limit = """                $manual_limit = ($range_from !== null && $range_to !== null) ? 50 : 10;
                if ($manual && $done >= $manual_limit) { $remaining++; continue; }
"""
assert old_limit in p
p = p.replace(old_limit, new_limit, 1)

old_report = """            update_option('tnw_last_report', $now->format('Y-m-d H:i') . "\nObsłużono: $done\nBez zmian: $unchanged\nPozostało w tym zakresie: $remaining\nKorekty opublikowanych wpisów znajdują się w ich edytorze." . $taxonomy_report, false);
"""
new_report = """            $range_report = ($range_from !== null && $range_to !== null) ? "\nZakres dat: $range_from – $range_to" : '';
            update_option('tnw_last_report', $now->format('Y-m-d H:i') . $range_report . "\nObsłużono: $done\nBez zmian: $unchanged\nPozostało w tym zakresie: $remaining\nKorekty opublikowanych wpisów znajdują się w ich edytorze." . $taxonomy_report, false);
"""
assert old_report in p
p = p.replace(old_report, new_report, 1)
core.write_text(p, encoding='utf-8')

loader = Path('wordpress/tenis-net-wyniki/tenis-net-wyniki.php')
l = loader.read_text(encoding='utf-8').replace(' * Version: 0.3.1', ' * Version: 0.4.0', 1)
loader.write_text(l, encoding='utf-8')

# Extend contract tests.
test = Path('tests/wyniki_news/wordpress_import_core_test.php')
t = test.read_text(encoding='utf-8')
t = t.replace(
    "return array('id'=>$source.':'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title.\"\\n\".$body),'date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());",
    "return array('id'=>$source.':'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title.\"\\n\".$body),'date_start'=>'2026-07-04','date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());",
    1,
)
range_test = r'''

$posts=array(); $meta=array(); $post_terms=array();
$a=entry(700,true,'weekend a','kluby'); $a['date_start']='2026-08-28'; $a['date_end']='2026-08-29';
$b=entry(701,true,'weekend b','cuply'); $b['date_start']='2026-08-30'; $b['date_end']='2026-08-30';
$c=entry(702,true,'outside','plt'); $c['date_start']='2026-09-05'; $c['date_end']='2026-09-05';
$feed['posts']=array($a,$b,$c);
Tenis_NET_Wyniki::import(true,'2026-08-29','2026-08-30');
check(count($posts)===2,'manual date range imports only overlapping tournaments');
check(isset($posts[1]) && isset($posts[2]),'date range includes tournament spanning into selected weekend');
'''
t += range_test
test.write_text(t, encoding='utf-8')

py_test = Path('tests/wyniki_news/test_date_range.py')
py_test.write_text("""import unittest\nfrom datetime import date\nfrom wyniki_news.build import overlaps_date_range\n\n\nclass DateRangeTests(unittest.TestCase):\n    def test_overlap_includes_spanning_tournament(self):\n        item = {'data_od': '2026-09-04', 'data_do': '2026-09-06'}\n        self.assertTrue(overlaps_date_range(item, date(2026, 9, 5), date(2026, 9, 6)))\n\n    def test_non_overlap_is_excluded(self):\n        item = {'data_od': '2026-08-29', 'data_do': '2026-08-30'}\n        self.assertFalse(overlaps_date_range(item, date(2026, 9, 5), date(2026, 9, 6)))\n\n\nif __name__ == '__main__':\n    unittest.main()\n""", encoding='utf-8')
