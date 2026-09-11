from pathlib import Path

plugin = Path('wordpress/tenis-net-wyniki/tenis-net-wyniki.php')
text = plugin.read_text(encoding='utf-8')

text = text.replace('Version: 0.1.1', 'Version: 0.2.0')
text = text.replace("tnw_schedule_version') !== '0.1.1'", "tnw_schedule_version') !== '0.2.0'")
text = text.replace("update_option('tnw_schedule_version', '0.1.1', false);", "update_option('tnw_schedule_version', '0.2.0', false);")
text = text.replace(
    'Pierwsza wersja obsługuje PLT. Pozostałe źródła będą dodawane oddzielnie.',
    'Obsługiwane źródła: PLT, Cuply, Kluby.org i PZT TOP. Niepełne lub niejednoznaczne wyniki pozostają szkicami do kontroli redakcyjnej.'
)
old = """        return preg_match('/^plt:[0-9]+$/', $e['id']) && preg_match('/^[a-f0-9]{64}$/', $e['fingerprint']) && hash_equals(hash('sha256', $e['title'] . \"\\n\" . $e['content']), $e['fingerprint']) &&\n            preg_match('/^\\d{4}-\\d{2}-\\d{2}$/', $e['date_end']) && $e['date_end'] > '2026-07-01' && isset($e['ready']) && is_bool($e['ready']);"""
new = """        $valid_id = preg_match('/^(?:plt|cuply|kluby):[0-9]+$/', $e['id']) ||\n            preg_match('/^pzt:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/', $e['id']);\n        return $valid_id && preg_match('/^[a-f0-9]{64}$/', $e['fingerprint']) && hash_equals(hash('sha256', $e['title'] . \"\\n\" . $e['content']), $e['fingerprint']) &&\n            preg_match('/^\\d{4}-\\d{2}-\\d{2}$/', $e['date_end']) && $e['date_end'] > '2026-07-01' && isset($e['ready']) && is_bool($e['ready']);"""
if old not in text:
    raise SystemExit('Nie znaleziono starej walidacji PLT w pluginie')
text = text.replace(old, new)
plugin.write_text(text, encoding='utf-8')

test = Path('tests/wyniki_news/wordpress_import_test.php')
t = test.read_text(encoding='utf-8')
old_fn = """function entry($id,$ready=true,$body='wyniki') {\n    $title='Turniej '.$id;\n    return array('id'=>'plt:'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title.\"\\n\".$body),'date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());\n}"""
new_fn = """function entry($id,$ready=true,$body='wyniki',$source='plt') {\n    $title='Turniej '.$source.':'.$id;\n    return array('id'=>$source.':'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title.\"\\n\".$body),'date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());\n}"""
if old_fn not in t:
    raise SystemExit('Nie znaleziono funkcji entry w teście WordPress')
t = t.replace(old_fn, new_fn)
extra = """

$posts=array(); $meta=array(); $feed['posts']=array(
    entry(301,true,'plt result','plt'),
    entry(91,true,'cuply result','cuply'),
    entry(10368,true,'kluby result','kluby'),
    entry('7B170278-F7BB-4B0A-BEA5-49A199E798BC',false,'pzt result','pzt')
);
Tenis_NET_Wyniki::import(true);
check(count($posts)===4,'plugin accepts PLT, Cuply, Kluby.org and PZT TOP identifiers');
check($posts[4]->post_status==='draft','PZT review item remains draft');
"""
if 'plugin accepts PLT, Cuply, Kluby.org and PZT TOP identifiers' not in t:
    t += extra
test.write_text(t, encoding='utf-8')
