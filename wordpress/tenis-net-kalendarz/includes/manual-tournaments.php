<?php
if (!defined('ABSPATH')) {
    exit;
}

final class Tenis_NET_Kalendarz_Manual {
    const POST_TYPE = 'tnk_tournament';
    const META_PREFIX = '_tnk_';

    public static function init() {
        add_action('init', array(__CLASS__, 'register_post_type'));
        add_action('add_meta_boxes', array(__CLASS__, 'add_meta_boxes'));
        add_action('save_post_' . self::POST_TYPE, array(__CLASS__, 'save'));
        add_filter('manage_' . self::POST_TYPE . '_posts_columns', array(__CLASS__, 'columns'));
        add_action('manage_' . self::POST_TYPE . '_posts_custom_column', array(__CLASS__, 'column_value'), 10, 2);
    }

    public static function register_post_type() {
        register_post_type(self::POST_TYPE, array(
            'labels' => array(
                'name' => 'Kalendarz turniejów',
                'singular_name' => 'Turniej',
                'menu_name' => 'Kalendarz turniejów',
                'name_admin_bar' => 'Turniej',
                'add_new' => 'Dodaj turniej',
                'add_new_item' => 'Dodaj nowy turniej',
                'edit_item' => 'Edytuj turniej',
                'new_item' => 'Nowy turniej',
                'view_item' => 'Podgląd turnieju',
                'search_items' => 'Szukaj turniejów',
                'not_found' => 'Nie znaleziono ręcznych turniejów',
                'not_found_in_trash' => 'Brak turniejów w koszu',
                'all_items' => 'Turnieje ręczne',
            ),
            'public' => false,
            'show_ui' => true,
            'show_in_menu' => true,
            'show_in_admin_bar' => true,
            'show_in_rest' => false,
            'menu_icon' => 'dashicons-calendar-alt',
            'supports' => array('title', 'editor', 'revisions'),
            'has_archive' => false,
            'rewrite' => false,
            'query_var' => false,
            'capability_type' => 'post',
            'map_meta_cap' => true,
        ));
    }

    private static function key($field) {
        return self::META_PREFIX . $field;
    }

    private static function value($post_id, $field) {
        return (string) get_post_meta($post_id, self::key($field), true);
    }

    private static function voivodeships() {
        return array(
            'dolnośląskie', 'kujawsko-pomorskie', 'lubelskie', 'lubuskie', 'łódzkie',
            'małopolskie', 'mazowieckie', 'opolskie', 'podkarpackie', 'podlaskie',
            'pomorskie', 'śląskie', 'świętokrzyskie', 'warmińsko-mazurskie',
            'wielkopolskie', 'zachodniopomorskie'
        );
    }

    public static function add_meta_boxes() {
        add_meta_box('tnk_tournament_data', 'Dane turnieju', array(__CLASS__, 'meta_box'), self::POST_TYPE, 'normal', 'high');
    }

    public static function meta_box($post) {
        wp_nonce_field('tnk_save_manual_tournament', 'tnk_manual_nonce');
        $v = function($field) use ($post) { return self::value($post->ID, $field); };
        $games = get_post_meta($post->ID, self::key('rodzaje_gry'), true);
        if (!is_array($games)) $games = array();
        ?>
        <style>
            .tnk-admin-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 20px}.tnk-admin-field{display:flex;flex-direction:column;gap:5px}.tnk-admin-field label{font-weight:600}.tnk-admin-field input,.tnk-admin-field select{width:100%;max-width:none}.tnk-admin-wide{grid-column:1/-1}.tnk-admin-checks{display:flex;gap:18px;flex-wrap:wrap;padding:7px 0}.tnk-admin-note{grid-column:1/-1;color:#646970;margin:0 0 4px}@media(max-width:782px){.tnk-admin-grid{grid-template-columns:1fr}.tnk-admin-wide{grid-column:auto}}
        </style>
        <div class="tnk-admin-grid">
            <p class="tnk-admin-note">Nazwa turnieju jest tytułem wpisu. Opis wpisz w głównym edytorze WordPress. Do kalendarza trafiają tylko opublikowane i nieprzeterminowane turnieje.</p>
            <div class="tnk-admin-field"><label for="tnk_data_od">Data rozpoczęcia *</label><input type="date" id="tnk_data_od" name="tnk[data_od]" value="<?php echo esc_attr($v('data_od')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_data_do">Data zakończenia</label><input type="date" id="tnk_data_do" name="tnk[data_do]" value="<?php echo esc_attr($v('data_do')); ?>"><span class="description">Jeśli puste, przyjmujemy datę rozpoczęcia.</span></div>
            <div class="tnk-admin-field"><label for="tnk_miasto">Miasto *</label><input type="text" id="tnk_miasto" name="tnk[miasto]" value="<?php echo esc_attr($v('miasto')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_wojewodztwo">Województwo</label><select id="tnk_wojewodztwo" name="tnk[wojewodztwo]"><option value="">— wybierz —</option><?php foreach(self::voivodeships() as $woj): ?><option value="<?php echo esc_attr($woj); ?>" <?php selected($v('wojewodztwo'), $woj); ?>><?php echo esc_html($woj); ?></option><?php endforeach; ?></select></div>
            <div class="tnk-admin-field"><label for="tnk_miejsce">Obiekt / miejsce</label><input type="text" id="tnk_miejsce" name="tnk[miejsce]" value="<?php echo esc_attr($v('miejsce')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_adres">Adres</label><input type="text" id="tnk_adres" name="tnk[adres]" value="<?php echo esc_attr($v('adres')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_cykl">Cykl</label><input type="text" id="tnk_cykl" name="tnk[cykl]" value="<?php echo esc_attr($v('cykl')); ?>" placeholder="np. Grand Prix Mazowsza"></div>
            <div class="tnk-admin-field"><label for="tnk_kategorie">Kategoria</label><input type="text" id="tnk_kategorie" name="tnk[kategorie]" value="<?php echo esc_attr($v('kategorie')); ?>" placeholder="np. OPEN, 45+, kobiety"></div>
            <div class="tnk-admin-field tnk-admin-wide"><label>Rodzaj gry</label><div class="tnk-admin-checks"><?php foreach(array('singiel'=>'Singiel','debel'=>'Debel','mikst'=>'Mikst') as $key=>$label): ?><label><input type="checkbox" name="tnk[rodzaje_gry][]" value="<?php echo esc_attr($key); ?>" <?php checked(in_array($key, $games, true)); ?>> <?php echo esc_html($label); ?></label><?php endforeach; ?></div></div>
            <div class="tnk-admin-field"><label for="tnk_wpisowe">Wpisowe</label><input type="text" id="tnk_wpisowe" name="tnk[wpisowe]" value="<?php echo esc_attr($v('wpisowe')); ?>" placeholder="np. 120 zł"></div>
            <div class="tnk-admin-field"><label for="tnk_termin_zgloszen">Termin zgłoszeń</label><input type="text" id="tnk_termin_zgloszen" name="tnk[termin_zgloszen]" value="<?php echo esc_attr($v('termin_zgloszen')); ?>" placeholder="np. 18.09.2026, 20:00"></div>
            <div class="tnk-admin-field"><label for="tnk_organizator">Organizator</label><input type="text" id="tnk_organizator" name="tnk[organizator]" value="<?php echo esc_attr($v('organizator')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_kontakt">Kontakt</label><input type="text" id="tnk_kontakt" name="tnk[kontakt]" value="<?php echo esc_attr($v('kontakt')); ?>" placeholder="telefon / e-mail"></div>
            <div class="tnk-admin-field"><label for="tnk_system_gier">System gier</label><input type="text" id="tnk_system_gier" name="tnk[system_gier]" value="<?php echo esc_attr($v('system_gier')); ?>" placeholder="np. grupy + puchar"></div>
            <div class="tnk-admin-field"><label for="tnk_nawierzchnia">Nawierzchnia</label><input type="text" id="tnk_nawierzchnia" name="tnk[nawierzchnia]" value="<?php echo esc_attr($v('nawierzchnia')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_limit_uczestnikow">Limit uczestników</label><input type="text" id="tnk_limit_uczestnikow" name="tnk[limit_uczestnikow]" value="<?php echo esc_attr($v('limit_uczestnikow')); ?>"></div>
            <div class="tnk-admin-field"><label for="tnk_poziom">Poziom / ograniczenia udziału</label><input type="text" id="tnk_poziom" name="tnk[poziom]" value="<?php echo esc_attr($v('poziom')); ?>"></div>
            <div class="tnk-admin-field tnk-admin-wide"><label for="tnk_url">Strona turnieju / zapisy</label><input type="url" id="tnk_url" name="tnk[url]" value="<?php echo esc_attr($v('url')); ?>" placeholder="https://..."></div>
        </div>
        <?php
    }

    public static function save($post_id) {
        if (!isset($_POST['tnk_manual_nonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['tnk_manual_nonce'])), 'tnk_save_manual_tournament')) return;
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
        if (wp_is_post_revision($post_id) || !current_user_can('edit_post', $post_id)) return;
        $raw = isset($_POST['tnk']) && is_array($_POST['tnk']) ? wp_unslash($_POST['tnk']) : array();
        $fields = array('data_od','data_do','miasto','wojewodztwo','miejsce','adres','cykl','kategorie','wpisowe','termin_zgloszen','organizator','kontakt','system_gier','nawierzchnia','limit_uczestnikow','poziom');
        foreach ($fields as $field) {
            $val = isset($raw[$field]) ? sanitize_text_field($raw[$field]) : '';
            if ($val === '') delete_post_meta($post_id, self::key($field)); else update_post_meta($post_id, self::key($field), $val);
        }
        $url = isset($raw['url']) ? esc_url_raw($raw['url']) : '';
        if ($url === '') delete_post_meta($post_id, self::key('url')); else update_post_meta($post_id, self::key('url'), $url);
        $allowed = array('singiel','debel','mikst');
        $games = isset($raw['rodzaje_gry']) && is_array($raw['rodzaje_gry']) ? array_values(array_intersect($allowed, array_map('sanitize_key', $raw['rodzaje_gry']))) : array();
        if ($games) update_post_meta($post_id, self::key('rodzaje_gry'), $games); else delete_post_meta($post_id, self::key('rodzaje_gry'));
    }

    private static function format_date($start, $end) {
        $s = DateTime::createFromFormat('Y-m-d', (string) $start);
        $e = DateTime::createFromFormat('Y-m-d', (string) $end);
        if (!$s) return (string) $start;
        if (!$e || $start === $end || !$end) return $s->format('d.m.Y');
        if ($s->format('Y-m') === $e->format('Y-m')) return $s->format('d') . '–' . $e->format('d.m.Y');
        return $s->format('d.m.Y') . '–' . $e->format('d.m.Y');
    }

    public static function columns($columns) {
        return array('cb'=>$columns['cb'],'title'=>'Turniej','tnk_date'=>'Termin','tnk_city'=>'Miasto','tnk_cycle'=>'Cykl','date'=>'Opublikowano');
    }

    public static function column_value($column, $post_id) {
        if ($column === 'tnk_date') echo esc_html(self::format_date(self::value($post_id, 'data_od'), self::value($post_id, 'data_do')));
        elseif ($column === 'tnk_city') echo esc_html(self::value($post_id, 'miasto'));
        elseif ($column === 'tnk_cycle') echo esc_html(self::value($post_id, 'cykl'));
    }

    public static function items() {
        $posts = get_posts(array('post_type'=>self::POST_TYPE,'post_status'=>'publish','numberposts'=>-1,'orderby'=>'ID','order'=>'ASC','suppress_filters'=>false));
        $today = current_time('Y-m-d');
        $items = array();
        foreach ($posts as $post) {
            $start = self::value($post->ID, 'data_od');
            if (!$start) continue;
            $end = self::value($post->ID, 'data_do');
            if (!$end) $end = $start;
            if ($end < $today) continue;
            $games = get_post_meta($post->ID, self::key('rodzaje_gry'), true);
            if (!is_array($games)) $games = array();
            $url = self::value($post->ID, 'url');
            $items[] = array(
                'id'=>'manual-'.$post->ID,
                'zrodlo'=>'Ręcznie',
                'organizacja'=>'Tenis NET',
                'cykl'=>self::value($post->ID, 'cykl'),
                'kategoria_zrodla'=>'',
                'nazwa'=>get_the_title($post),
                'data_od'=>$start,
                'data_do'=>$end,
                'miasto'=>self::value($post->ID, 'miasto'),
                'wojewodztwo'=>self::value($post->ID, 'wojewodztwo'),
                'miejsce'=>self::value($post->ID, 'miejsce'),
                'adres'=>self::value($post->ID, 'adres'),
                'kategorie'=>self::value($post->ID, 'kategorie'),
                'rodzaje_gry'=>$games,
                'wpisowe'=>self::value($post->ID, 'wpisowe'),
                'termin_zgloszen'=>self::value($post->ID, 'termin_zgloszen'),
                'organizator'=>self::value($post->ID, 'organizator'),
                'kontakt'=>self::value($post->ID, 'kontakt'),
                'system_gier'=>self::value($post->ID, 'system_gier'),
                'nawierzchnia'=>self::value($post->ID, 'nawierzchnia'),
                'limit_uczestnikow'=>self::value($post->ID, 'limit_uczestnikow'),
                'poziom'=>self::value($post->ID, 'poziom'),
                'url'=>$url,
                'zapisy_url'=>$url,
                'opis'=>wp_strip_all_tags($post->post_content),
                'status'=>($start <= $today && $today <= $end) ? 'trwa' : 'nadchodzacy',
            );
        }
        return $items;
    }
}
