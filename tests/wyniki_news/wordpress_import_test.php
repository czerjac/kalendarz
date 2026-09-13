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
