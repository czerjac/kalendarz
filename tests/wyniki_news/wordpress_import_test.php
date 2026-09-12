<?php
// Isolated importer contract test with in-memory WordPress functions, not a live WP test.
define('ABSPATH', __DIR__);
$options = array('tnw_settings' => array('enabled'=>true,'mode'=>'publish','category'=>1,'author'=>1));
$posts = array(); $meta = array(); $post_terms = array(); $categories = array(); $tags = array();
$feed = array('schema_version'=>1, 'run_date'=>'2000-01-01', 'posts'=>array());
function add_action(...$a) {} function register_activation_hook(...$a) {} function register_deactivation_hook(...$a) {}
function wp_parse_args($a,$b) { return array_merge($b,$a); }
function get_option($k,$d=false) { global $options; return $options[$k] ?? $d; }
function update_option($k,$v,...$a) { global $options; $options[$k]=$v; }
function add_option($k,$v,...$a) { global $options; if(isset($options[$k]))return false; $options[$k]=$v; return true; }
function delete_option($k) { global $options; unset($options[$k]); }
function user_can(...$a) { return true; }
function wp_remote_get(...$a) { global $feed; return $feed; }
function is_wp_error($v) { return false; }
function wp_remote_retrieve_response_code($r) { return 200; }
function wp_remote_retrieve_body($r) { return json_encode($r); }
function get_posts($q) { global $posts,$meta; foreach($posts as $p) {
    if(isset($q['name']) && $p->post_name === $q['name'])return array(clone $p);
    if(isset($q['meta_key']) && ($meta[$p->ID][$q['meta_key']]??null)===$q['meta_value'])return array(clone $p);
} return array(); }
function get_post_meta($id,$key,...$a) { global $meta; return $meta[$id][$key]??''; }
function update_post_meta($id,$key,$value) { global $meta; $meta[$id][$key]=$value; }
function sanitize_text_field($s) { return strip_tags($s); }
function sanitize_title($s) {
    $s=strtolower($s);
    $s=strtr($s,array('ą'=>'a','ć'=>'c','ę'=>'e','ł'=>'l','ń'=>'n','ó'=>'o','ś'=>'s','ź'=>'z','ż'=>'z'));
    return trim(preg_replace('/[^a-z0-9]+/','-',$s),'-');
}
function get_term_by($field,$value,$taxonomy) {
    global $categories,$tags; $pool=$taxonomy==='category'?$categories:$tags;
    foreach($pool as $term) {
        if(($field==='slug' && $term->slug===$value)||($field==='name' && $term->name===$value))return clone $term;
    }
    return false;
}
function wp_set_post_terms($id,$ids,$taxonomy,$append=false) { global $post_terms; $post_terms[$id][$taxonomy]=$ids; return $ids; }
function wp_kses_post($s) { return $s; }
function wp_slash($v) { return $v; }
function wp_insert_post($fields,...$a) { global $posts; $id=$fields['ID']??count($posts)+1; $fields['ID']=$id; $posts[$id]=(object)$fields; return $id; }
function get_post($id) { global $posts; return clone $posts[$id]; }
function check($condition,$message) { if(!$condition)throw new Exception($message); echo 'OK '.$message.PHP_EOL; }
function entry($id,$ready=true,$body='wyniki',$source='plt') {
    $title='Turniej '.$source.':'.$id;
    return array('id'=>$source.':'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title."\n".$body),'date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());
}
require __DIR__.'/../../wordpress/tenis-net-wyniki/tenis-net-wyniki.php';
$feed['posts']=array(entry(1)); Tenis_NET_Wyniki::import(true);
check(count($posts)===1 && $posts[1]->post_status==='publish','confirmed article published');
Tenis_NET_Wyniki::import(true); check(count($posts)===1,'same feed is idempotent');
$feed['posts']=array(entry(1,true,'changed')); Tenis_NET_Wyniki::import(true);
check($posts[1]->post_content==='wyniki' && $meta[1]['_tnw_pending']['content']==='changed','published content preserved and correction staged');
$feed['posts']=array(entry(2,false)); Tenis_NET_Wyniki::import(true);
check($posts[2]->post_status==='draft','incomplete result stays draft');
$feed['posts']=array(entry(2,true,'complete')); Tenis_NET_Wyniki::import(true);
check($posts[2]->post_status==='publish','completed machine draft can publish');
$feed['posts']=array(entry(3,false)); Tenis_NET_Wyniki::import(true); $posts[3]->post_content='EDITOR CHANGE';
$feed['posts']=array(entry(3,true,'complete')); Tenis_NET_Wyniki::import(true);
check($posts[3]->post_content==='EDITOR CHANGE' && isset($meta[3]['_tnw_pending']),'editor changes never overwritten');
$posts[3]->post_status='trash'; Tenis_NET_Wyniki::import(true); check(count($posts)===3,'trash does not regenerate a post');
$feed['posts']=array(entry(4)); Tenis_NET_Wyniki::import(false); check(count($posts)===3,'old feed not used for automatic weekly import');
$options['tnw_import_lock']=time(); Tenis_NET_Wyniki::import(true); check(count($posts)===3,'atomic lock prevents overlapping imports'); unset($options['tnw_import_lock']);
$feed['posts']=array(entry(4)); $feed['posts'][0]['content']='tampered'; Tenis_NET_Wyniki::import(true); check(count($posts)===3,'invalid fingerprint rejected');
$feed['posts']=array(); for($i=10;$i<23;$i++)$feed['posts'][]=entry($i);
Tenis_NET_Wyniki::import(true); check(count($posts)===13,'backfill batch limited to ten');
Tenis_NET_Wyniki::import(true); check(count($posts)===16,'next batch continues without duplicates');
$now = new DateTimeImmutable('now', new DateTimeZone('Europe/Warsaw'));
$tuesday = $now->modify('tuesday this week')->setTime(4,0);
if ($now < $tuesday) $tuesday = $tuesday->modify('-7 days');
$posts=array(); $meta=array(); $post_terms=array(); $feed['run_date']=$tuesday->format('Y-m-d'); $feed['posts']=array();
for($i=100;$i<113;$i++) { $e=entry($i); $e['date_end']=$tuesday->modify('-7 days')->format('Y-m-d'); $feed['posts'][]=$e; }
$old=entry(200); $old['date_end']=$tuesday->modify('-8 days')->format('Y-m-d'); $feed['posts'][]=$old;
$future=entry(201); $future['date_end']=$tuesday->format('Y-m-d'); $feed['posts'][]=$future;
Tenis_NET_Wyniki::import(false);
check(count($posts)===13,'one weekly import processes all entries and only previous seven days');
$next=Tenis_NET_Wyniki::next_run(new DateTimeImmutable('2026-10-20 05:00',new DateTimeZone('Europe/Warsaw')));
check($next->format('Y-m-d H:i P')==='2026-10-27 04:30 +01:00','weekly time survives autumn clock change');

$posts=array(); $meta=array(); $post_terms=array(); $feed['posts']=array(
    entry(301,true,'plt result','plt'),
    entry(91,true,'cuply result','cuply'),
    entry(10368,true,'kluby result','kluby'),
    entry('7B170278-F7BB-4B0A-BEA5-49A199E798BC',false,'pzt result','pzt')
);
Tenis_NET_Wyniki::import(true);
check(count($posts)===4,'plugin accepts PLT, Cuply, Kluby.org and PZT TOP identifiers');
check($posts[4]->post_status==='draft','PZT review item remains draft');

$posts=array(); $meta=array(); $post_terms=array();
$categories=array((object)array('term_id'=>7,'name'=>'mazowieckie','slug'=>'mazowieckie'));
$tags=array((object)array('term_id'=>11,'name'=>'Grand Prix Mazowsza','slug'=>'grand-prix-mazowsza'));
$entry = entry(500,true,'regional result','kluby');
$entry['voivodeship']='mazowieckie';
$entry['cycle']='Grand Prix Mazowsza';
$entry['tags']=array('Grand Prix Mazowsza');
$feed['posts']=array($entry); Tenis_NET_Wyniki::import(true);
check($posts[1]->post_category===array(7),'voivodeship selects existing WordPress category');
check(($post_terms[1]['post_tag']??array())===array(11),'controlled cycle selects existing WordPress tag');

$posts=array(); $meta=array(); $post_terms=array();
$entry = entry(501,true,'fallback result','kluby');
$entry['voivodeship']='mazowieckie';
$entry['tags']=array('Nieistniejący tag');
$entry['fingerprint']=hash('sha256',$entry['title']."\n".$entry['content']);
$feed['posts']=array($entry); Tenis_NET_Wyniki::import(true);
check($posts[1]->post_category===array(7),'existing regional category still applies when tag is unsupported');
check(($post_terms[1]['post_tag']??array())===array(),'unsupported tag is never created or assigned');
