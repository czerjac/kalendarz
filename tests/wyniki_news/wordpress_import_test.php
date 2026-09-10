<?php
// Isolated importer contract test with in-memory WordPress functions, not a live WP test.
define('ABSPATH', __DIR__);
$options = array('tnw_settings' => array('enabled'=>true,'mode'=>'publish','category'=>1,'author'=>1));
$posts = array(); $meta = array(); $feed = array('schema_version'=>1, 'run_date'=>'2000-01-01', 'posts'=>array());
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
function wp_kses_post($s) { return $s; }
function wp_slash($v) { return $v; }
function wp_insert_post($fields,...$a) { global $posts; $id=$fields['ID']??count($posts)+1; $fields['ID']=$id; $posts[$id]=(object)$fields; return $id; }
function get_post($id) { global $posts; return clone $posts[$id]; }
function check($condition,$message) { if(!$condition)throw new Exception($message); echo 'OK '.$message.PHP_EOL; }
function entry($id,$ready=true,$body='wyniki') {
    $title='Turniej '.$id;
    return array('id'=>'plt:'.$id,'title'=>$title,'content'=>$body,'fingerprint'=>hash('sha256',$title."\n".$body),'date_end'=>'2026-07-04','ready'=>$ready,'issues'=>array());
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
