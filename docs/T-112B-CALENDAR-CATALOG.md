# T-112b — katalog do wybierania wyników, także bez RAW

**21.11.2026.** Uwaga architektoniczna: `Tournament` w Django bywa
tworzony dopiero po wczytaniu RAW. Turniej znany z kalendarza, ale bez
opublikowanych wyników, nie ma jeszcze własnego `Tournament` w DB.
Dlatego nie wolno ograniczać panelu pobierania wyników do queryset
`Tournament`.

Istniejący `wyniki_news.build.discover()` czyta bieżący i archiwalny
kalendarz. Z połączonego `state['known']` generujemy publiczną lekką
`data/wyniki_news/selected_catalog.json` (bez zawodników, meczów,
kontaktów). Każda pozycja zawiera URL, nazwę, źródło, daty, miasto oraz
stan wyników. Pokazujemy również turnieje bez rekordu `results`.
Dane wynikowe rozpoznajemy po dotychczasowym `metadata_for_result`;
brak próby ma stan UNCHECKED, nie NO_RESULTS.

Plik odświeża tygodniowy workflow istniejących newsów oraz każdy
ręczny wybór wyników. `feed.json` nadal obsługuje wyłącznie newsy od
lipca 2026. Katalog GP Tour obejmuje turnieje od 1 stycznia 2026.
Nie tworzymy w TenisOne sztucznych RAW ani Player.
