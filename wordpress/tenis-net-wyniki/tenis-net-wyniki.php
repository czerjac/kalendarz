<?php
/**
 * Plugin Name: Tenis NET – Wyniki i newsy
 * Description: Importuje osobny plik wyników z GitHuba do zwykłych wpisów. Nie zmienia kalendarza.
 * Version: 0.3.2
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

function tnw_032_migrate_existing_draft_categories() {
    if (get_option('tnw_category_migration_version', '') === '0.3.2') { return; }
    if (function_exists('current_user_can') && !current_user_can('manage_options')) { return; }

    $response = wp_remote_get(Tenis_NET_Wyniki::FEED, array(
        'timeout' => 40,
        'limit_response_size' => 15 * 1024 * 1024,
    ));
    if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) { return; }
    $feed = json_decode(wp_remote_retrieve_body($response), true);
    if (!is_array($feed) || ($feed['schema_version'] ?? null) !== 1 || !isset($feed['posts']) || !is_array($feed['posts'])) { return; }

    $by_id = array();
    foreach ($feed['posts'] as $entry) {
        if (!is_array($entry) || empty($entry['id']) || empty($entry['voivodeship']) || !is_string($entry['voivodeship'])) { continue; }
        $by_id[$entry['id']] = $entry['voivodeship'];
    }

    $drafts = get_posts(array(
        'post_type' => 'post',
        'post_status' => 'draft',
        'meta_key' => '_tnw_id',
        'numberposts' => -1,
    ));
    $updated = 0; $skipped = 0;
    foreach ($drafts as $post) {
        $tnw_id = get_post_meta($post->ID, '_tnw_id', true);
        if (!$tnw_id || !isset($by_id[$tnw_id])) { $skipped++; continue; }

        // Only untouched machine-generated drafts are eligible for automatic migration.
        $generated_hash = get_post_meta($post->ID, '_tnw_generated_hash', true);
        $current_hash = hash('sha256', $post->post_title . "\n" . $post->post_content);
        if (!$generated_hash || !hash_equals($generated_hash, $current_hash)) { $skipped++; continue; }

        $voivodeship = sanitize_text_field($by_id[$tnw_id]);
        $slug = tnw_031_voivodeship_slug($voivodeship);
        if ($slug === '') { $skipped++; continue; }
        $term = get_term_by('slug', $slug, 'category');
        if (!$term || is_wp_error($term)) { $term = get_term_by('name', $slug, 'category'); }
        if (!$term || is_wp_error($term)) { $skipped++; continue; }

        wp_set_post_categories($post->ID, array((int) $term->term_id), false);
        update_post_meta($post->ID, '_tnw_voivodeship', $voivodeship);
        $updated++;
    }

    update_option('tnw_category_migration_report', '0.3.2: poprawiono ' . $updated . ', pominięto ' . $skipped . '.', false);
    update_option('tnw_category_migration_version', '0.3.2', false);
}

add_action('added_post_meta', 'tnw_031_apply_voivodeship_category', 10, 4);
add_action('updated_post_meta', 'tnw_031_apply_voivodeship_category', 10, 4);
add_action('admin_init', 'tnw_032_migrate_existing_draft_categories');

register_activation_hook(__FILE__, array('Tenis_NET_Wyniki', 'activate'));
register_deactivation_hook(__FILE__, array('Tenis_NET_Wyniki', 'deactivate'));
