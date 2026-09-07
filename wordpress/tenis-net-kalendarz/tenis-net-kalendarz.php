<?php
/**
 * Plugin Name: Tenis NET – Kalendarz turniejów amatorskich
 * Description: Wyświetla agregowany kalendarz turniejów amatorskich z danych JSON generowanych w repozytorium czerjac/kalendarz.
 * Version: 0.1.1
 * Author: Tenis NET
 * Text Domain: tenis-net-kalendarz
 */

if (!defined('ABSPATH')) {
    exit;
}

final class Tenis_NET_Kalendarz {
    const VERSION = '0.1.1';
    const OPTION_URL = 'tnk_data_url';
    const OPTION_BACKUP = 'tnk_last_good_json';
    const TRANSIENT = 'tnk_calendar_data_v1';
    const DEFAULT_URL = 'https://raw.githubusercontent.com/czerjac/kalendarz/main/data/turnieje.json';
    const CACHE_TTL = 900;

    public static function init() {
        add_shortcode('tenis_kalendarz', array(__CLASS__, 'shortcode'));
        add_action('admin_menu', array(__CLASS__, 'admin_menu'));
        add_action('admin_init', array(__CLASS__, 'register_settings'));
        add_action('admin_post_tnk_clear_cache', array(__CLASS__, 'clear_cache_action'));
    }

    public static function activate() {
        if (get_option(self::OPTION_URL, '') === '') {
            add_option(self::OPTION_URL, self::DEFAULT_URL, '', false);
        }
        if (get_option(self::OPTION_BACKUP, null) === null) {
            add_option(self::OPTION_BACKUP, '', '', false);
        }
    }

    public static function register_settings() {
        register_setting('tnk_settings', self::OPTION_URL, array(
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => self::DEFAULT_URL,
        ));
    }

    public static function admin_menu() {
        add_options_page('Kalendarz Tenis NET', 'Kalendarz Tenis NET', 'manage_options', 'tenis-net-kalendarz', array(__CLASS__, 'settings_page'));
    }

    public static function settings_page() {
        if (!current_user_can('manage_options')) return;
        $url = get_option(self::OPTION_URL, self::DEFAULT_URL);
        ?>
        <div class="wrap">
            <h1>Kalendarz Tenis NET</h1>
            <p>Wstaw shortcode <code>[tenis_kalendarz]</code> w treści dowolnej strony WordPress.</p>
            <form method="post" action="options.php">
                <?php settings_fields('tnk_settings'); ?>
                <table class="form-table" role="presentation"><tr>
                    <th scope="row"><label for="tnk_data_url">Adres pliku JSON</label></th>
                    <td><input type="url" class="regular-text code" id="tnk_data_url" name="<?php echo esc_attr(self::OPTION_URL); ?>" value="<?php echo esc_attr($url); ?>" />
                    <p class="description">Domyślnie dane są pobierane z publicznego repozytorium GitHub projektu kalendarza.</p></td>
                </tr></table>
                <?php submit_button('Zapisz ustawienia'); ?>
            </form>
            <hr><h2>Pamięć podręczna</h2>
            <p>Dane są buforowane przez 15 minut. Gdy źródło jest chwilowo niedostępne, wtyczka użyje ostatniej poprawnie pobranej kopii.</p>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <input type="hidden" name="action" value="tnk_clear_cache">
                <?php wp_nonce_field('tnk_clear_cache'); ?>
                <?php submit_button('Wyczyść cache teraz', 'secondary', 'submit', false); ?>
            </form>
        </div>
        <?php
    }

    public static function clear_cache_action() {
        if (!current_user_can('manage_options')) wp_die('Brak uprawnień.');
        check_admin_referer('tnk_clear_cache');
        delete_transient(self::TRANSIENT);
        wp_safe_redirect(add_query_arg(array('page' => 'tenis-net-kalendarz', 'cache' => 'cleared'), admin_url('options-general.php')));
        exit;
    }

    private static function fetch_data() {
        $cached = get_transient(self::TRANSIENT);
        if (is_array($cached) && !empty($cached['turnieje'])) {
            $cached['_tnk_stale'] = false;
            return $cached;
        }
        $url = get_option(self::OPTION_URL, self::DEFAULT_URL);
        if (!$url) $url = self::DEFAULT_URL;
        $response = wp_remote_get($url, array(
            'timeout' => 15,
            'redirection' => 4,
            'headers' => array('Accept' => 'application/json', 'User-Agent' => 'TenisNET-Kalendarz/' . self::VERSION . '; ' . home_url('/')),
        ));
        if (!is_wp_error($response) && 200 === (int) wp_remote_retrieve_response_code($response)) {
            $body = wp_remote_retrieve_body($response);
            $data = json_decode($body, true);
            if (is_array($data) && isset($data['turnieje']) && is_array($data['turnieje'])) {
                set_transient(self::TRANSIENT, $data, self::CACHE_TTL);
                update_option(self::OPTION_BACKUP, $body, false);
                $data['_tnk_stale'] = false;
                return $data;
            }
        }
        $backup = get_option(self::OPTION_BACKUP, '');
        if ($backup) {
            $data = json_decode($backup, true);
            if (is_array($data) && isset($data['turnieje']) && is_array($data['turnieje'])) {
                $data['_tnk_stale'] = true;
                return $data;
            }
        }
        return new WP_Error('tnk_no_data', 'Nie udało się pobrać danych kalendarza i nie ma jeszcze zapisanej kopii zapasowej.');
    }

    private static function enqueue_assets() {
        $base = plugin_dir_url(__FILE__);
        wp_enqueue_style('tenis-net-kalendarz', $base . 'assets/calendar.css', array(), self::VERSION);
        wp_enqueue_script('tenis-net-kalendarz', $base . 'assets/calendar.js', array(), self::VERSION, true);
    }

    private static function clean($value) { return trim(preg_replace('/\s+/u', ' ', (string) $value)); }

    private static function list_values($items, $field) {
        $values = array();
        foreach ($items as $item) {
            $value = isset($item[$field]) ? self::clean($item[$field]) : '';
            if ($value !== '') $values[$value] = true;
        }
        $values = array_keys($values); natcasesort($values); return array_values($values);
    }

    private static function flatten_values($items, $field) {
        $values = array();
        foreach ($items as $item) {
            if (empty($item[$field]) || !is_array($item[$field])) continue;
            foreach ($item[$field] as $value) { $value = self::clean($value); if ($value !== '') $values[$value] = true; }
        }
        $values = array_keys($values); natcasesort($values); return array_values($values);
    }

    private static function format_date($start, $end) {
        $s = DateTime::createFromFormat('Y-m-d', (string) $start);
        $e = DateTime::createFromFormat('Y-m-d', (string) $end);
        if (!$s) return self::clean($start);
        if (!$e || $start === $end) return $s->format('d.m.Y');
        if ($s->format('Y-m') === $e->format('Y-m')) return $s->format('d') . '–' . $e->format('d.m.Y');
        return $s->format('d.m.Y') . '–' . $e->format('d.m.Y');
    }

    private static function details_lines($item) {
        $map = array('cykl'=>'Cykl','kategoria_zrodla'=>'Kategoria','miejsce'=>'Miejsce','adres'=>'Adres','organizator'=>'Organizator','wpisowe'=>'Wpisowe','termin_zgloszen'=>'Termin zgłoszeń','system_gier'=>'System gier','limit_uczestnikow'=>'Limit uczestników','nawierzchnia'=>'Nawierzchnia','kontakt'=>'Kontakt','poziom'=>'Poziom');
        $lines = array();
        foreach ($map as $key=>$label) { $value = isset($item[$key]) ? self::clean($item[$key]) : ''; if ($value !== '') $lines[] = array($label,$value); }
        return $lines;
    }

    private static function details_url($item) {
        if (!empty($item['zapisy_url'])) return esc_url($item['zapisy_url']);
        if (!empty($item['url'])) return esc_url($item['url']);
        return '';
    }

    private static function badges($item) {
        $badges = array();
        if (!empty($item['rodzaje_gry']) && is_array($item['rodzaje_gry'])) foreach ($item['rodzaje_gry'] as $kind) $badges[] = self::clean($kind);
        return $badges;
    }

    private static function item_search_text($item) {
        $parts = array(isset($item['nazwa'])?$item['nazwa']:'',isset($item['miasto'])?$item['miasto']:'',isset($item['miejsce'])?$item['miejsce']:'',isset($item['organizator'])?$item['organizator']:'',isset($item['kategorie'])?$item['kategorie']:'',isset($item['cykl'])?$item['cykl']:'');
        return self::clean(implode(' ', $parts));
    }

    public static function shortcode($atts=array()) {
        self::enqueue_assets();
        $data = self::fetch_data();
        if (is_wp_error($data)) return '<div class="tnk tnk-error">' . esc_html($data->get_error_message()) . '</div>';
        $items = isset($data['turnieje']) && is_array($data['turnieje']) ? $data['turnieje'] : array();
        usort($items, function($a,$b){$ka=(isset($a['data_od'])?$a['data_od']:'').'|'.(isset($a['miasto'])?$a['miasto']:'').'|'.(isset($a['nazwa'])?$a['nazwa']:'');$kb=(isset($b['data_od'])?$b['data_od']:'').'|'.(isset($b['miasto'])?$b['miasto']:'').'|'.(isset($b['nazwa'])?$b['nazwa']:'');return strcmp($ka,$kb);});
        $wojewodztwa=self::list_values($items,'wojewodztwo'); $organizacje=self::list_values($items,'organizacja'); $cykle=self::list_values($items,'cykl'); $rodzaje=self::flatten_values($items,'rodzaje_gry');
        $id=wp_unique_id('tnk-'); $generated=!empty($data['wygenerowano_utc'])?$data['wygenerowano_utc']:''; $generated_text='';
        if($generated){try{$dt=new DateTime($generated);$dt->setTimezone(wp_timezone());$generated_text=$dt->format('d.m.Y H:i');}catch(Exception $e){$generated_text='';}}
        ob_start(); ?>
        <section class="tnk" id="<?php echo esc_attr($id); ?>" data-tnk-calendar>
            <div class="tnk-header"><div><p class="tnk-lead">Turnieje amatorskie z całej Polski w jednym miejscu.</p></div><div class="tnk-meta"><?php if($generated_text):?><span>Aktualizacja danych: <?php echo esc_html($generated_text); ?></span><?php endif;?><?php if(!empty($data['_tnk_stale'])):?><span class="tnk-stale">Pokazujemy ostatnią zapisaną kopię danych.</span><?php endif;?></div></div>
            <div class="tnk-filters" aria-label="Filtry kalendarza">
                <label class="tnk-field tnk-field-search"><span>Szukaj</span><input type="search" data-tnk-filter="search" placeholder="Turniej, miasto, cykl…" autocomplete="off"></label>
                <label class="tnk-field"><span>Termin</span><select data-tnk-filter="period"><option value="all">Wszystkie</option><option value="7">Najbliższe 7 dni</option><option value="30" selected>Najbliższe 30 dni</option><option value="90">Najbliższe 90 dni</option></select></label>
                <label class="tnk-field"><span>Województwo</span><select data-tnk-filter="wojewodztwo"><option value="">Wszystkie</option><?php foreach($wojewodztwa as $value):?><option value="<?php echo esc_attr($value); ?>"><?php echo esc_html($value); ?></option><?php endforeach;?></select></label>
                <label class="tnk-field"><span>Cykl</span><select data-tnk-filter="cykl"><option value="">Wszystkie</option><?php foreach($cykle as $value):?><option value="<?php echo esc_attr($value); ?>"><?php echo esc_html($value); ?></option><?php endforeach;?></select></label>
                <label class="tnk-field"><span>Rodzaj gry</span><select data-tnk-filter="rodzaj"><option value="">Wszystkie</option><?php foreach($rodzaje as $value):?><option value="<?php echo esc_attr($value); ?>"><?php echo esc_html(ucfirst($value)); ?></option><?php endforeach;?></select></label>
                <button type="button" class="tnk-reset" data-tnk-reset>Wyczyść filtry</button>
            </div>
            <div class="tnk-toolbar"><strong><span data-tnk-count><?php echo esc_html(count($items)); ?></span> turniejów</strong><span class="tnk-toolbar-note">Kliknij „Szczegóły”, aby zobaczyć więcej informacji.</span></div>
            <div class="tnk-table-wrap"><table class="tnk-table"><thead><tr><th>Data</th><th>Turniej</th><th>Miejscowość</th><th>Kategorie</th><th></th></tr></thead><tbody>
            <?php foreach($items as $index=>$item):$details_id=$id.'-detail-'.$index;$game_types=!empty($item['rodzaje_gry'])&&is_array($item['rodzaje_gry'])?implode('|',$item['rodzaje_gry']):'';$lines=self::details_lines($item);$link=self::details_url($item);?>
                <tr class="tnk-row" data-tnk-item data-start="<?php echo esc_attr(isset($item['data_od'])?$item['data_od']:''); ?>" data-end="<?php echo esc_attr(isset($item['data_do'])?$item['data_do']:''); ?>" data-wojewodztwo="<?php echo esc_attr(isset($item['wojewodztwo'])?$item['wojewodztwo']:''); ?>" data-organizacja="<?php echo esc_attr(isset($item['organizacja'])?$item['organizacja']:''); ?>" data-cykl="<?php echo esc_attr(isset($item['cykl'])?$item['cykl']:''); ?>" data-rodzaje="<?php echo esc_attr($game_types); ?>" data-search="<?php echo esc_attr(self::item_search_text($item)); ?>">
                    <td class="tnk-date"><?php echo esc_html(self::format_date(isset($item['data_od'])?$item['data_od']:'',isset($item['data_do'])?$item['data_do']:'')); ?></td><td><strong class="tnk-title"><?php echo esc_html(isset($item['nazwa'])?$item['nazwa']:''); ?></strong><?php if(!empty($item['cykl'])):?><span class="tnk-cycle"><?php echo esc_html($item['cykl']); ?></span><?php endif;?></td><td><?php echo esc_html(isset($item['miasto'])?$item['miasto']:''); ?></td><td><?php if(!empty($item['kategorie'])):?><span><?php echo esc_html($item['kategorie']); ?></span><?php endif;?><?php foreach(self::badges($item) as $badge):?><span class="tnk-badge"><?php echo esc_html($badge); ?></span><?php endforeach;?></td><td class="tnk-actions"><button type="button" class="tnk-details-button" aria-expanded="false" aria-controls="<?php echo esc_attr($details_id); ?>" data-tnk-toggle="<?php echo esc_attr($details_id); ?>">Szczegóły</button></td>
                </tr>
                <tr class="tnk-detail-row" id="<?php echo esc_attr($details_id); ?>" data-tnk-detail hidden><td colspan="5"><div class="tnk-detail-box"><dl><?php foreach($lines as $line):?><div><dt><?php echo esc_html($line[0]); ?></dt><dd><?php echo esc_html($line[1]); ?></dd></div><?php endforeach;?></dl><?php if(!empty($item['opis'])):?><p class="tnk-description"><?php echo esc_html($item['opis']); ?></p><?php endif;?><?php if($link):?><a class="tnk-link" href="<?php echo $link; ?>" target="_blank" rel="noopener noreferrer">Zapisz się / strona turnieju ↗</a><?php endif;?></div></td></tr>
            <?php endforeach;?></tbody></table></div>
            <div class="tnk-cards">
            <?php foreach($items as $index=>$item):$card_id=$id.'-card-'.$index;$game_types=!empty($item['rodzaje_gry'])&&is_array($item['rodzaje_gry'])?implode('|',$item['rodzaje_gry']):'';$lines=self::details_lines($item);$link=self::details_url($item);?>
                <article class="tnk-card" data-tnk-item data-start="<?php echo esc_attr(isset($item['data_od'])?$item['data_od']:''); ?>" data-end="<?php echo esc_attr(isset($item['data_do'])?$item['data_do']:''); ?>" data-wojewodztwo="<?php echo esc_attr(isset($item['wojewodztwo'])?$item['wojewodztwo']:''); ?>" data-organizacja="<?php echo esc_attr(isset($item['organizacja'])?$item['organizacja']:''); ?>" data-cykl="<?php echo esc_attr(isset($item['cykl'])?$item['cykl']:''); ?>" data-rodzaje="<?php echo esc_attr($game_types); ?>" data-search="<?php echo esc_attr(self::item_search_text($item)); ?>">
                    <div class="tnk-card-top"><span class="tnk-card-date"><?php echo esc_html(self::format_date(isset($item['data_od'])?$item['data_od']:'',isset($item['data_do'])?$item['data_do']:'')); ?></span></div><h3><?php echo esc_html(isset($item['nazwa'])?$item['nazwa']:''); ?></h3><div class="tnk-card-place"><?php echo esc_html(isset($item['miasto'])?$item['miasto']:''); ?><?php if(!empty($item['wojewodztwo'])):?> · <?php echo esc_html($item['wojewodztwo']); ?><?php endif;?></div><?php if(!empty($item['cykl'])):?><div class="tnk-cycle"><?php echo esc_html($item['cykl']); ?></div><?php endif;?><div class="tnk-card-badges"><?php foreach(self::badges($item) as $badge):?><span class="tnk-badge"><?php echo esc_html($badge); ?></span><?php endforeach;?></div><button type="button" class="tnk-details-button" aria-expanded="false" aria-controls="<?php echo esc_attr($card_id); ?>" data-tnk-toggle="<?php echo esc_attr($card_id); ?>">Szczegóły</button><div class="tnk-card-detail" id="<?php echo esc_attr($card_id); ?>" data-tnk-detail hidden><dl><?php foreach($lines as $line):?><div><dt><?php echo esc_html($line[0]); ?></dt><dd><?php echo esc_html($line[1]); ?></dd></div><?php endforeach;?></dl><?php if(!empty($item['opis'])):?><p class="tnk-description"><?php echo esc_html($item['opis']); ?></p><?php endif;?><?php if($link):?><a class="tnk-link" href="<?php echo $link; ?>" target="_blank" rel="noopener noreferrer">Zapisz się / strona turnieju ↗</a><?php endif;?></div>
                </article>
            <?php endforeach;?></div>
            <div class="tnk-empty" data-tnk-empty hidden>Brak turniejów spełniających wybrane kryteria.</div>
        </section>
        <?php return ob_get_clean();
    }
}

register_activation_hook(__FILE__, array('Tenis_NET_Kalendarz', 'activate'));
Tenis_NET_Kalendarz::init();
