# Wyniki i newsy — PLT + Cuply + Kluby.org + PZT TOP

Osobny dodatek do istniejącego kalendarza. Nie zmienia jego wtyczki, zbierania danych ani archiwum. Czyta kalendarz i archiwum, zapisuje wyłącznie `data/wyniki_news/`.

## Zakres

- Turnieje PLT, Cuply, Kluby.org i PZT TOP zakończone **po 1 lipca 2026**, przed dniem pobrania. Jeden turniej źródłowy = jeden zwykły wpis WordPress.
- Neutralny wstęp, zwycięzca finału gdy istnieje jeden potwierdzony finał, listy meczów według faz, wyniki A:B, link do źródła. Bez dopisywania relacji z przebiegu spotkań.
- Dane sportowe: nazwiska, identyfikatory zawodników/par, wyniki, faza, kategoria źródłowa i turniej. Profile kontaktowe nie są zapisywane.
- **PLT**: publiczne dane wynikowe pobierane przez istniejący adapter PLT.
- **Cuply**: publiczny komponent Livewire obsługiwany zwykłymi żądaniami HTTP; produkcyjny kolektor nie wymaga Playwrighta ani Chromium. Adapter obsługuje singiel/debel, grupy + play-off, super tie-breaki i walkowery.
- **Kluby.org**: serwerowo renderowane strony `/mecze` i `/kolejnosc`, pobierane przez `requests` + BeautifulSoup. Adapter obsługuje singiel, debel/mikst, grupy + play-off, wiele drabinek oraz weryfikację finału z klasyfikacją końcową.
- **PZT TOP**: publiczne `TournamentMatchesPlay.aspx`, `TournamentMatches.aspx?QS=...` i `TournamentTabResults.aspx`. Adapter zachowuje `EventID`, obsługuje singiel/debel, grupy, drabinki, BYE, walkowery, krecze i super tie-breaki.
- PZT TOP i Kluby.org mogą publikować kilka konkurencji w jednym turnieju. Wszystkie mecze są pobierane i zachowują kategorię źródłową, ale turniej wielokategoriowy pozostaje szkicem do kontroli redakcyjnej, ponieważ obecny model newsa ma tylko jeden główny `final_id`.
- Niepełne lub sprzeczne dane blokują automatyczną publikację: wpis pozostaje szkicem. Nie jest to gwarancja poprawności samego źródła.
- Adaptery nie scalają automatycznie tożsamości zawodników ani turniejów pomiędzy serwisami.

## Harmonogram

`wyniki-newsy.yml`: wtorek 04:00, `Europe/Warsaw` (uwzględnia czas letni). GitHub może opóźnić zadanie; harmonogram wymaga aktywnego workflow na głównej gałęzi. Ręczne uruchomienie jest dostępne w Actions.

Kolektor sprawdza wyłącznie turnieje zakończone w poprzednich siedmiu dniach kalendarzowych: wtorek–poniedziałek. WordPress odbiera tylko zestaw z ostatniego wtorku i tylko ten sam zakres siedmiu dni. Nie ma automatycznego uzupełniania starszych wyników. Starsze przygotowane archiwum pozostaje dostępne przez przycisk w panelu; jego ponowne pobranie ze źródeł wymaga ręcznego polecenia `python -m wyniki_news.build --backfill`.

Wtyczka odbiera plik raz w tygodniu, we wtorek o 04:30 czasu polskiego, po przygotowaniu danych przez GitHub. Automatyczny import obejmuje cały tygodniowy zestaw; limit 10 dotyczy tylko ręcznego importu archiwum. Nie ma godzinowego sprawdzania ani automatycznych ponowień. WP-Cron zależy od ruchu: aby wykonać odbiór bez odwiedzin, wystarczy uruchomienie WordPress Cron na hostingu raz we wtorek o 04:30. Nie zmieniaj harmonogramów wymaganych przez inne wtyczki. GitHub może opóźnić zadanie; gdy świeżego zestawu zabraknie, w raporcie będzie komunikat i potrzebny będzie import ręczny. Godzina rozpoczęcia zbierania nie jest gwarancją dokładnej godziny publikacji.

## Instalacja

1. Zrób kopię zapasową WordPressa. Zainstaluj ZIP `tenis-net-wyniki-0.1.1.zip` przez Wtyczki → Dodaj nową → Wyślij wtyczkę; włącz. Jeśli masz wersję 0.1.0, wybierz zastąpienie aktualnej wtyczki nową wersją. Godzinowe zadanie zostanie usunięte automatycznie; ustawienia i wpisy pozostaną. Nie usuwaj wtyczki kalendarza.
2. Narzędzia → Wyniki Tenis NET: wybierz kategorię i autora. Pozostaw szkice oraz wyłączony odbiór automatyczny. Zapisz.
3. Importuj pierwszych 10 turniejów i sprawdź je w sekcji Wpisy → Szkice: wygląd tabel, polskie znaki, źródło i kategorię.
4. Gdy próbka jest poprawna, możesz opublikować te szkice zwykłymi narzędziami WordPressa. Zmiana trybu nie publikuje automatycznie identycznych szkiców już zaimportowanych.
5. W ustawieniach dodatku wybierz automatyczną publikację potwierdzonych wyników. Importuj kolejne partie archiwum, aż raport pokaże zero pozostałych. Niepełne i wielokategoriowe wpisy nadal zostają szkicami. Archiwalne newsy mają bieżącą datę publikacji, a termin turnieju w tytule i treści.
6. Zaznacz cotygodniowy odbiór i zapisz. Uzgodnij z hostingiem uruchamianie WordPress Cron, jeśli publikacja ma następować bez nocnego ruchu.

Ponowny import nie tworzy kopii. Opublikowanych i ręcznie poprawionych wpisów dodatek nie nadpisuje. Proponowana korekta pojawia się w edytorze wpisu w sekcji Wyniki Tenis NET; jej zastosowanie jest świadomą decyzją redaktora. Usunięte do kosza wpisy nie są odtwarzane.

Wyłączenie dodatku zatrzymuje odbiór, ale pozostawia wpisy. Nie potrzeba udostępniać hasła WordPressa ani tokena GitHuba — wtyczka pobiera publiczny plik wyników.

## Testy i granice weryfikacji

`python -m unittest discover -s tests/wyniki_news -v`

`php -l wordpress/tenis-net-wyniki/tenis-net-wyniki.php`

`php tests/wyniki_news/wordpress_import_test.php`

Testy PHP wykorzystują symulowane funkcje WordPressa; nie zastępują testu na docelowym WordPressie. Pierwsza instalacja i próbka szkiców są konieczne przed włączeniem automatycznej publikacji.

Dane: `stan.json` — stan i mecze; `feed.json` — gotowe treści; `raport.json` — kompletność i błędy. Uruchomienie: `python -m wyniki_news.build`. Zależności produkcyjne: requests 2.32.5, beautifulsoup4 4.13.5.
