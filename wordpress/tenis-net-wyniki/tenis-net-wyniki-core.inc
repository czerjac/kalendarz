<?php
/**
 * Plugin Name: Tenis NET – Wyniki i newsy
 * Description: Importuje osobny plik wyników z GitHuba do zwykłych wpisów. Nie zmienia kalendarza.
 * Version: 0.3.0
 * Requires PHP: 7.4
 * Author: Tenis NET
 */
if (!defined('ABSPATH')) { exit; }

final class Tenis_NET_Wyniki {
    const FEED = 'https://raw.githubusercontent.com/czerjac/kalendarz/main/data/wyniki_news/feed.json';
    const OPTION = 'tnw_settings';
    const HOOK = 'tnw_check_weekly_feed';

    public static function init() {
        add_action('init', array(__CLASS__, 'migrate_schedule'));
        add_action('admin_menu', array(__CLASS__, 'menu'));
        add_action('admin_post_tnw_save', array(__CLASS__, 'save'));
        add_action('admin_post_tnw_import', array(__CLASS__, 'manual'));
        add_action(self::HOOK, array(__CLASS__, 'scheduled'));
        add_action('add_meta_boxes', function() {
            add_meta_box('tnw_source', 'Wyniki Tenis NET — aktualizacja źródła', array(__CLASS__, 'metabox'), 'post', 'normal');
        });
        add_action('admin_post_tnw_apply', array(__CLASS__, 'apply'));
    }

    public static function activate() {
        self::migrate_schedule();
        if (!get_option(self::OPTION)) {
            add_option(self::OPTION, array('enabled' => false, 'mode' => 'draft', 'category' => 0, 'author' => get_current_user_id()), '', false);
        }
    }

    public static function next_run($now) {
        $next = $now->setTimezone(new DateTimeZone('Europe/Warsaw'))->modify('tuesday this week')->setTime(4, 30);
        return $next <= $now ? $next->modify('+7 days') : $next;
    }

    public static function migrate_schedule() {
        if (get_option('tnw_schedule_version') !== '0.2.0') {
            wp_clear_scheduled_hook(self::HOOK);
            update_option('tnw_schedule_version', '0.2.0', false);
        }
        if (!wp_next_scheduled(self::HOOK)) {
            wp_schedule_single_event(self::next_run(new DateTimeImmutable('now'))->getTimestamp(), self::HOOK);
        }
    }

    public static function deactivate() { wp_clear_scheduled_hook(self::HOOK); }
    public static function menu() { add_management_page('Wyniki Tenis NET', 'Wyniki Tenis NET', 'manage_options', 'tnw', array(__CLASS__, 'page')); }
    private static function settings() { return wp_parse_args(get_option(self::OPTION, array()), array('enabled' => false, 'mode' => 'draft', 'category' => 0, 'author' => 0)); }
    private static function guard() { if (!current_user_can('manage_options')) { wp_die('Brak uprawnień.'); } }

    public static function page() {
        self::guard(); $s = self::settings();
        echo '<div class="wrap"><h1>Wyniki i newsy Tenis NET</h1><p>Obsługiwane źródła: PLT, Cuply, Kluby.org i PZT TOP. Niepełne lub niejednoznaczne wyniki pozostają szkicami do kontroli redakcyjnej.</p>';
        echo '<p>Kategoria wpisu jest dobierana automatycznie według województwa. Tagi są przypisywane tylko dla ustalonych źródeł i cykli. Wtyczka nie tworzy nowych kategorii ani tagów.</p>';
        echo '<p>GitHub zbiera wyniki raz w tygodniu, we wtorek o 04:00 czasu polskiego, z poprzednich siedmiu dni (wtorek–poniedziałek). WordPress odbiera zestaw raz, o 04:30, aby dać czas na jego przygotowanie. Nie ma godzinowego sprawdzania ani automatycznych ponowień. Przy braku ruchu wystarczy cotygodniowe uruchomienie WordPress Cron przez hosting we wtorek o 04:30. GitHub może opóźnić zbieranie; brak świeżego zestawu zostanie zapisany w raporcie.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="tnw_save">';
        wp_nonce_field('tnw_save');
        echo '<p><label><input type="checkbox" name="enabled" value="1" ' . checked($s['enabled'], true, false) . '> Włącz cotygodniowy odbiór newsów</label></p>';
        echo '<p><label>Nowe wpisy: <select name="mode"><option value="draft" ' . selected($s['mode'], 'draft', false) . '>Szkice do sprawdzenia</option><option value="publish" ' . selected($s['mode'], 'publish', false) . '>Publikuj automatycznie potwierdzone wyniki</option></select></label></p>';
        echo '<p>Kategoria awaryjna (gdy brak województwa lub odpowiedniej kategorii): '; wp_dropdown_categories(array('hide_empty' => 0, 'name' => 'category', 'selected' => $s['category'], 'show_option_none' => 'Wybierz kategorię', 'option_none_value' => 0)); echo '</p>';
        echo '<p>Autor wpisów: '; wp_dropdown_users(array('name' => 'author', 'selected' => $s['author'], 'capability' => 'publish_posts')); echo '</p>';
        submit_button('Zapisz ustawienia'); echo '</form><hr>';
        echo '<h2>Archiwalne newsy</h2><p>Każde kliknięcie obsłuży do 10 nowych lub zmienionych turniejów. Ponowne uruchomienie nie tworzy kopii. Archiwalne artykuły otrzymują bieżącą datę publikacji; data turnieju jest w treści. Niepełne wyniki zawsze trafiają do szkiców.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="tnw_import">'; wp_nonce_field('tnw_import'); submit_button('Importuj kolejne 10 turniejów od lipca', 'secondary'); echo '</form>';
        echo '<h2>Ostatni przebieg</h2><pre>' . esc_html(get_option('tnw_last_report', 'Jeszcze nie uruchomiono.')) . '</pre></div>';
    }

    public static function save() {
        self::guard(); check_admin_referer('tnw_save');
        $mode = isset($_POST['mode']) && $_POST['mode'] === 'publish' ? 'publish' : 'draft';
        if ($mode === 'publish' && !current_user_can('publish_posts')) { wp_die('Brak prawa publikacji.'); }
        $category = absint($_POST['category'] ?? 0); $author = absint($_POST['author'] ?? 0);
        $term = get_term($category, 'category');
        if (!$category || !$term || is_wp_error($term) || !user_can($author, 'publish_posts')) { wp_die('Wybierz istniejącą kategorię awaryjną i autora z prawem publikacji.'); }
        update_option(self::OPTION, array('enabled' => !empty($_POST['enabled']), 'mode' => $mode, 'category' => $category, 'author' => $author), false);
        wp_safe_redirect(admin_url('tools.php?page=tnw')); exit;
    }

    public static function manual() {
        self::guard(); check_admin_referer('tnw_import'); self::import(true);
        wp_safe_redirect(admin_url('tools.php?page=tnw')); exit;
    }

    public static function scheduled() {
        self::migrate_schedule();
        $s = self::settings(); if (empty($s['enabled'])) { return; }
        self::import(false);
    }

    private static function allowed_voivodeships() {
        return array(
            'dolnośląskie', 'kujawsko-pomorskie', 'lubelskie', 'lubuskie', 'łódzkie',
            'małopolskie', 'mazowieckie', 'opolskie', 'podkarpackie', 'podlaskie',
            'pomorskie', 'śląskie', 'świętokrzyskie', 'warmińsko-mazurskie',
            'wielkopolskie', 'zachodniopomorskie'
        );
    }

    private static function allowed_tags() {
        return array(
            'Tenis Open Polska PZT', 'Polska Liga Tenisa', 'Cuply',
            'Grand Prix Mazowsza', 'Grand Prix Wybrzeża', 'Grand Prix Podlasia i Mazur'
        );
    }

    private static function category_for($entry, $fallback, &$notes) {
        $name = isset($entry['voivodeship']) ? sanitize_text_field($entry['voivodeship']) : '';
        if ($name !== '') {
            if (!in_array($name, self::allowed_voivodeships(), true)) {
                $notes[] = 'Nieobsługiwane województwo: ' . $name;
                return (int) $fallback;
            }
            $term = get_term_by('slug', sanitize_title($name), 'category');
            if (!$term || is_wp_error($term)) { $term = get_term_by('name', $name, 'category'); }
            if ($term && !is_wp_error($term)) { return (int) $term->term_id; }
            $notes[] = 'Nie znaleziono kategorii województwa: ' . $name;
        }
        return (int) $fallback;
    }

    private static function tag_ids($entry, &$notes) {
        $ids = array();
        $names = isset($entry['tags']) && is_array($entry['tags']) ? $entry['tags'] : array();
        foreach ($names as $name) {
            $name = sanitize_text_field($name);
            if ($name === '') { continue; }
            if (!in_array($name, self::allowed_tags(), true)) {
                $notes[] = 'Pominięto nieobsługiwany tag: ' . $name;
                continue;
            }
            $term = get_term_by('slug', sanitize_title($name), 'post_tag');
            if (!$term || is_wp_error($term)) { $term = get_term_by('name', $name, 'post_tag'); }
            if ($term && !is_wp_error($term)) { $ids[] = (int) $term->term_id; }
            else { $notes[] = 'Nie znaleziono tagu: ' . $name; }
        }
        return array_values(array_unique($ids));
    }

    public static function import($manual) {
        $s = self::settings();
        if (!$s['category'] || !user_can($s['author'], 'publish_posts')) { update_option('tnw_last_report', 'Najpierw wybierz kategorię awaryjną i autora.', false); return; }
        // Atomic lock; stale lock recovery after a crashed PHP request.
        $lock = (int) get_option('tnw_import_lock', 0);
        if ($lock && $lock < time() - 900) { delete_option('tnw_import_lock'); }
        if (!add_option('tnw_import_lock', time(), '', false)) { return; }
        try {
            $response = wp_remote_get(self::FEED, array('timeout' => 40, 'limit_response_size' => 15 * 1024 * 1024));
            if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) { throw new Exception('Nie udało się pobrać pliku wyników. Poprzednie wpisy zachowano.'); }
            $feed = json_decode(wp_remote_retrieve_body($response), true);
            if (!is_array($feed) || ($feed['schema_version'] ?? null) !== 1 || !isset($feed['posts']) || !is_array($feed['posts'])) { throw new Exception('Nieprawidłowy plik wyników.'); }
            $now = new DateTimeImmutable('now', new DateTimeZone('Europe/Warsaw'));
            $tuesday = $now->modify('tuesday this week')->setTime(4, 0);
            if ($now < $tuesday) { $tuesday = $tuesday->modify('-7 days'); }
            if (!$manual && ($feed['run_date'] ?? '') !== $tuesday->format('Y-m-d')) {
                update_option('tnw_last_report', 'Brak świeżego wtorkowego zestawu. Nie ponawiano automatycznie; można użyć importu ręcznego.', false); return;
            }
            $done = 0; $unchanged = 0; $remaining = 0; $taxonomy_notes = array();
            foreach ($feed['posts'] as $entry) {
                if (!self::valid($entry)) { throw new Exception('Nieprawidłowy rekord wyników; przerwano import.'); }
                if (!$manual) {
                    $end = $entry['date_end'];
                    // Exactly the previous seven calendar days, Tuesday through Monday.
                    if ($end < $tuesday->modify('-7 days')->format('Y-m-d') || $end >= $tuesday->format('Y-m-d')) { continue; }
                }
                $slug = 'tnw-' . str_replace(':', '-', $entry['id']);
                $existing = get_posts(array('name' => $slug, 'post_type' => 'post', 'post_status' => array('publish', 'draft', 'pending', 'future', 'private', 'trash'), 'numberposts' => 1));
                if (!$existing) { $existing = get_posts(array('meta_key' => '_tnw_id', 'meta_value' => $entry['id'], 'post_type' => 'post', 'post_status' => array('publish', 'draft', 'pending', 'future', 'private', 'trash'), 'numberposts' => 1)); }
                $post = $existing ? $existing[0] : null;
                if ($post && get_post_meta($post->ID, '_tnw_id', true) !== $entry['id']) { throw new Exception('Konflikt adresu wpisu — wymagana ręczna kontrola: ' . $slug); }
                if ($post && (get_post_meta($post->ID, '_tnw_fingerprint', true) === $entry['fingerprint'] || get_post_meta($post->ID, '_tnw_pending_fingerprint', true) === $entry['fingerprint'] || $post->post_status === 'trash')) { $unchanged++; continue; }
                if ($manual && $done >= 10) { $remaining++; continue; }
                if ($post) {
                    // Keep published and manually edited posts intact; expose a proposed correction.
                    $last = get_post_meta($post->ID, '_tnw_generated_hash', true);
                    $edited = $last !== hash('sha256', $post->post_title . "\n" . $post->post_content);
                    if ($post->post_status !== 'draft' || $edited) {
                        update_post_meta($post->ID, '_tnw_pending', wp_slash($entry));
                        update_post_meta($post->ID, '_tnw_pending_fingerprint', $entry['fingerprint']);
                        $done++; continue;
                    }
                }
                $category_id = self::category_for($entry, $s['category'], $taxonomy_notes);
                $tag_ids = self::tag_ids($entry, $taxonomy_notes);
                $fields = array(
                    'post_title' => sanitize_text_field($entry['title']),
                    'post_content' => wp_kses_post($entry['content']),
                    'post_name' => $slug,
                    'post_type' => 'post',
                    'post_author' => $s['author'],
                    'post_category' => array($category_id),
                    'post_status' => ($entry['ready'] === true && $s['mode'] === 'publish') ? 'publish' : 'draft'
                );
                if ($post) { $fields['ID'] = $post->ID; }
                $id = wp_insert_post(wp_slash($fields), true);
                if (is_wp_error($id)) { throw new Exception('Nie udało się zapisać wpisu: ' . $entry['id']); }
                wp_set_post_terms($id, $tag_ids, 'post_tag', false);
                update_post_meta($id, '_tnw_id', $entry['id']);
                self::metadata($id, $entry); $done++;
            }
            $taxonomy_notes = array_values(array_unique($taxonomy_notes));
            $taxonomy_report = $taxonomy_notes ? "\nUwagi kategorii/tagów:\n- " . implode("\n- ", $taxonomy_notes) : '';
            update_option('tnw_last_report', $now->format('Y-m-d H:i') . "\nObsłużono: $done\nBez zmian: $unchanged\nPozostało w tym zakresie: $remaining\nKorekty opublikowanych wpisów znajdują się w ich edytorze." . $taxonomy_report, false);
        } catch (Exception $e) { update_option('tnw_last_report', $e->getMessage(), false); }
        finally { delete_option('tnw_import_lock'); }
    }

    private static function valid($e) {
        if (!is_array($e)) { return false; }
        foreach (array('id', 'title', 'content', 'fingerprint', 'date_end') as $key) { if (!isset($e[$key]) || !is_string($e[$key]) || !$e[$key]) { return false; } }
        if (isset($e['voivodeship']) && !is_string($e['voivodeship'])) { return false; }
        if (isset($e['cycle']) && !is_string($e['cycle'])) { return false; }
        if (isset($e['tags']) && (!is_array($e['tags']) || count(array_filter($e['tags'], 'is_string')) !== count($e['tags']))) { return false; }
        $valid_id = preg_match('/^(?:plt|cuply|kluby):[0-9]+$/', $e['id']) ||
            preg_match('/^pzt:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/', $e['id']);
        return $valid_id && preg_match('/^[a-f0-9]{64}$/', $e['fingerprint']) && hash_equals(hash('sha256', $e['title'] . "\n" . $e['content']), $e['fingerprint']) &&
            preg_match('/^\d{4}-\d{2}-\d{2}$/', $e['date_end']) && $e['date_end'] > '2026-07-01' && isset($e['ready']) && is_bool($e['ready']);
    }

    private static function metadata($id, $entry) {
        update_post_meta($id, '_tnw_fingerprint', $entry['fingerprint']);
        $post = get_post($id);
        update_post_meta($id, '_tnw_generated_hash', hash('sha256', $post->post_title . "\n" . $post->post_content));
        update_post_meta($id, '_tnw_issues', $entry['issues'] ?? array());
        update_post_meta($id, '_tnw_voivodeship', $entry['voivodeship'] ?? '');
        update_post_meta($id, '_tnw_cycle', $entry['cycle'] ?? '');
        update_post_meta($id, '_tnw_tags', $entry['tags'] ?? array());
    }

    public static function metabox($post) {
        if (!get_post_meta($post->ID, '_tnw_id', true)) { echo '<p>Ten wpis nie pochodzi z importu wyników.</p>'; return; }
        echo '<p>' . esc_html(implode('; ', (array) get_post_meta($post->ID, '_tnw_issues', true))) . '</p>';
        $pending = get_post_meta($post->ID, '_tnw_pending', true);
        if (!$pending) { echo '<p>Brak oczekujących aktualizacji.</p>'; return; }
        echo '<p>Źródło zmieniło wyniki. Poniżej nowa wersja. Zastosowanie zastąpi obecną treść i tytuł, także własne poprawki; WordPress zachowa rewizję.</p><details><summary>Podgląd nowej treści</summary>' . wp_kses_post($pending['content']) . '</details>';
        $url = wp_nonce_url(admin_url('admin-post.php?action=tnw_apply&post_id=' . $post->ID), 'tnw_apply_' . $post->ID);
        echo '<p><a class="button" href="' . esc_url($url) . '">Zastosuj tę wersję</a></p>';
    }

    public static function apply() {
        $id = absint($_GET['post_id'] ?? 0); if (!current_user_can('edit_post', $id)) { wp_die('Brak uprawnień.'); }
        check_admin_referer('tnw_apply_' . $id); $entry = get_post_meta($id, '_tnw_pending', true);
        if (!self::valid($entry)) { wp_die('Brak poprawnej aktualizacji.'); }
        if (get_post_status($id) === 'publish' && !current_user_can('publish_posts')) { wp_die('Brak uprawnień publikacji.'); }
        $settings = self::settings(); $notes = array();
        $category_id = self::category_for($entry, $settings['category'], $notes);
        $tag_ids = self::tag_ids($entry, $notes);
        $result = wp_update_post(wp_slash(array(
            'ID' => $id,
            'post_title' => sanitize_text_field($entry['title']),
            'post_content' => wp_kses_post($entry['content']),
            'post_category' => array($category_id)
        )), true);
        if (is_wp_error($result)) { wp_die('Nie zapisano aktualizacji.'); }
        wp_set_post_terms($id, $tag_ids, 'post_tag', false);
        self::metadata($id, $entry); delete_post_meta($id, '_tnw_pending'); delete_post_meta($id, '_tnw_pending_fingerprint');
        wp_safe_redirect(get_edit_post_link($id, 'raw')); exit;
    }
}
Tenis_NET_Wyniki::init();
register_activation_hook(__FILE__, array('Tenis_NET_Wyniki', 'activate'));
register_deactivation_hook(__FILE__, array('Tenis_NET_Wyniki', 'deactivate'));
