<?php
/**
 * Plugin Name: Tenis NET – Wyniki i newsy
 * Description: Importuje osobny plik wyników z GitHuba do zwykłych wpisów. Nie zmienia kalendarza.
 * Version: 0.4.0
 * Requires PHP: 7.4
 * Author: Tenis NET
 */
if (!defined('ABSPATH')) { exit; }

require_once __DIR__ . '/tenis-net-wyniki-core.inc';

function tnw_031_voivodeship_slug($name) {
    $key = sanitize_title(sanitize_text_field($name));
    $map = array(
        'dolnoslaskie' => 'dolnoslaskie',
        'kujawsko-pomorskie' => 'kujawsko-pomorskie',
        'lubelskie' => 'lubelskie',
        'lubuskie' => 'lubuskie',
        'lodzkie' => 'lodzkie',
        'malopolskie' => 'malopolskie',
        'mazowieckie' => 'mazowieckie',
        'opolskie' => 'opolskie',
        'podkarpackie' => 'podkarpackie',
        'podlaskie' => 'podlaskie',
        'pomorskie' => 'pomorskie',
        'slaskie' => 'slaskie',
        'swietokrzyskie' => 'swietokrzyskie',
        'warminsko-mazurskie' => 'warminsko-mazurskie',
        'wielkopolskie' => 'wielkopolskie',
        'zachodniopomorskie' => 'zachodnio-pomorskie',
        'zachodnio-pomorskie' => 'zachodnio-pomorskie'
    );
    return isset($map[$key]) ? $map[$key] : '';
}

function tnw_031_apply_voivodeship_category($meta_id, $post_id, $meta_key, $meta_value) {
    if ($meta_key !== '_tnw_voivodeship' || !is_string($meta_value) || $meta_value === '') { return; }
    $slug = tnw_031_voivodeship_slug($meta_value);
    if ($slug === '') { return; }
    $term = get_term_by('slug', $slug, 'category');
    if (!$term || is_wp_error($term)) { $term = get_term_by('name', $slug, 'category'); }
    if ($term && !is_wp_error($term)) {
        wp_set_post_categories($post_id, array((int) $term->term_id), false);
    }
}

add_action('added_post_meta', 'tnw_031_apply_voivodeship_category', 10, 4);
add_action('updated_post_meta', 'tnw_031_apply_voivodeship_category', 10, 4);

register_activation_hook(__FILE__, array('Tenis_NET_Wyniki', 'activate'));
register_deactivation_hook(__FILE__, array('Tenis_NET_Wyniki', 'deactivate'));
