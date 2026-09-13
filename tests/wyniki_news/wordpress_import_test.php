<?php
$tnw_set_categories = array();
function wp_set_post_categories($post_id, $ids, $append=false) {
    global $tnw_set_categories;
    $tnw_set_categories[$post_id] = $ids;
    return $ids;
}

require __DIR__ . '/wordpress_import_core_test.php';

check(tnw_031_voivodeship_slug('dolnośląskie') === 'dolnoslaskie', 'accented Lower Silesia maps to simplified WordPress slug');
check(tnw_031_voivodeship_slug('zachodniopomorskie') === 'zachodnio-pomorskie', 'West Pomerania maps to custom WordPress slug');

$categories = array((object)array('term_id'=>8,'name'=>'zachodnio-pomorskie','slug'=>'zachodnio-pomorskie'));
tnw_031_apply_voivodeship_category(1, 77, '_tnw_voivodeship', 'zachodniopomorskie');
check(($tnw_set_categories[77] ?? array()) === array(8), 'voivodeship metadata applies existing WordPress category');

// 0.3.2 repairs categories of existing untouched imported drafts even when their content fingerprint did not change.
$posts=array(); $meta=array(); $post_terms=array(); $tnw_set_categories=array();
unset($options['tnw_category_migration_version'], $options['tnw_category_migration_report']);
$categories=array((object)array('term_id'=>9,'name'=>'wielkopolskie','slug'=>'wielkopolskie'));
$tags=array();
$feed=array(
    'schema_version'=>1,
    'run_date'=>'2026-09-13',
    'posts'=>array(array('id'=>'plt:5143','voivodeship'=>'wielkopolskie')),
);
$posts[1]=(object)array('ID'=>1,'post_type'=>'post','post_status'=>'draft','post_name'=>'tnw-plt-5143','post_title'=>'Machine draft','post_content'=>'unchanged');
$meta[1]=array('_tnw_id'=>'plt:5143','_tnw_generated_hash'=>hash('sha256',"Machine draft\nunchanged"));
$posts[2]=(object)array('ID'=>2,'post_type'=>'post','post_status'=>'publish','post_name'=>'tnw-plt-5143-published','post_title'=>'Published','post_content'=>'unchanged');
$meta[2]=array('_tnw_id'=>'plt:5143','_tnw_generated_hash'=>hash('sha256',"Published\nunchanged"));
$posts[3]=(object)array('ID'=>3,'post_type'=>'post','post_status'=>'draft','post_name'=>'tnw-plt-5143-edited','post_title'=>'Edited draft','post_content'=>'EDITOR CHANGE');
$meta[3]=array('_tnw_id'=>'plt:5143','_tnw_generated_hash'=>hash('sha256',"Edited draft\noriginal machine text"));

tnw_032_migrate_existing_draft_categories();
check(($tnw_set_categories[1]??array())===array(9),'0.3.2 migration repairs category on untouched imported draft');
check(($meta[1]['_tnw_voivodeship']??'')==='wielkopolskie','0.3.2 migration stores recovered voivodeship metadata');
check(!isset($tnw_set_categories[2]),'0.3.2 migration never changes published imported post');
check(!isset($tnw_set_categories[3]),'0.3.2 migration never changes manually edited draft');
check(($options['tnw_category_migration_version']??'')==='0.3.2','0.3.2 category migration is recorded as one-time');
