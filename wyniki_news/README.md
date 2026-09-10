# Wyniki i newsy — pierwsza wersja PLT

Osobny dodatek do istniejącego kalendarza. Nie zmienia jego wtyczki, zbierania danych ani archiwum. Czyta kalendarz i archiwum, zapisuje wyłącznie `data/wyniki_news/`.

## Zakres

- Turnieje PLT zakończone **po 1 lipca 2026**, przed dniem pobrania. Jeden turniej = jeden zwykły wpis WordPress.
- Neutralny wstęp, zwycięzca finału gdy potwierdzony, listy meczów według faz, wyniki A:B, link do źródła. Bez dopisywania relacji z przebiegu spotkań.
- Dane sportowe: nazwiska, identyfikatory zawodników/par, wyniki, faza i turniej. Profile kontaktowe nie są zapisywane.
- PZT TOP, Cuply i Kluby.org nie są jeszcze obsługiwane. Liczba oczekujących turniejów widnieje w raporcie.
- Niepełne lub sprzeczne dane blokują automatyczną publikację: wpis pozostaje szkicem. Nie jest to gwarancja poprawności samego źródła.

## Harmonogram

`wyniki-newsy.yml`: wtorek 04:00, `Europe/Warsaw` (uwzględnia czas letni). GitHub może opóźnić zadanie; harmonogram wymaga aktywnego workflow na głównej gałęzi. Ręczne uruchomienie jest dostępne w Actions.

Kolektor sprawdza nowe zakończone turnieje, ostatnie 35 dni i raz w tygodniu starsze niepełne wyniki. WordPress automatycznie odbiera tylko zestaw z ostatniego wtorku, uwzględniając ostatnie 35 dni, aby nadrobić spóźnione wyniki. Obejmuje również turnieje rozegrane w dni robocze. Starsze archiwum importuje się przyciskiem w panelu. Potwierdzone stare wyniki poza oknem 35 dni nie są ponownie sprawdzane.

Wtyczka sprawdza plik co godzinę i przetwarza po 10 zmian. WP-Cron zależy od ruchu. Aby publikować nad ranem także bez odwiedzin, hosting powinien uruchamiać WordPress Cron co 5–10 minut. Sam harmonogram GitHuba nie gwarantuje dokładnej godziny publikacji.

## Instalacja

1. Zrób kopię zapasową WordPressa. Zainstaluj ZIP `tenis-net-wyniki-0.1.0.zip` przez Wtyczki → Dodaj nową → Wyślij wtyczkę; włącz. Nie usuwaj wtyczki kalendarza.
2. Narzędzia → Wyniki Tenis NET: wybierz kategorię i autora. Pozostaw szkice oraz wyłączony odbiór automatyczny. Zapisz.
3. Importuj pierwszych 10 turniejów i sprawdź je w sekcji Wpisy → Szkice: wygląd tabel, polskie znaki, źródło i kategorię.
4. Gdy próbka jest poprawna, możesz opublikować te szkice zwykłymi narzędziami WordPressa. Zmiana trybu nie publikuje automatycznie identycznych szkiców już zaimportowanych.
5. W ustawieniach dodatku wybierz automatyczną publikację potwierdzonych wyników. Importuj kolejne partie archiwum, aż raport pokaże zero pozostałych. Niepełne wpisy nadal zostają szkicami. Archiwalne newsy mają bieżącą datę publikacji, a termin turnieju w tytule i treści.
6. Zaznacz cotygodniowy odbiór i zapisz. Uzgodnij z hostingiem uruchamianie WordPress Cron, jeśli publikacja ma następować bez nocnego ruchu.

Ponowny import nie tworzy kopii. Opublikowanych i ręcznie poprawionych wpisów dodatek nie nadpisuje. Proponowana korekta pojawia się w edytorze wpisu w sekcji Wyniki Tenis NET; jej zastosowanie jest świadomą decyzją redaktora. Usunięte do kosza wpisy nie są odtwarzane.

Wyłączenie dodatku zatrzymuje odbiór, ale pozostawia wpisy. Nie potrzeba udostępniać hasła WordPressa ani tokena GitHuba — wtyczka pobiera publiczny plik wyników.

## Testy i granice weryfikacji

`python -m unittest discover -s tests/wyniki_news -v`

`php -l wordpress/tenis-net-wyniki/tenis-net-wyniki.php`

`php tests/wyniki_news/wordpress_import_test.php`

Testy PHP wykorzystują symulowane funkcje WordPressa; nie zastępują testu na docelowym WordPressie. Pierwsza instalacja i próbka szkiców są konieczne przed włączeniem automatycznej publikacji.

Dane: `stan.json` — stan i mecze; `feed.json` — gotowe treści; `raport.json` — kompletność i błędy. Uruchomienie: `python -m wyniki_news.build`. Zależności: requests 2.32.5, beautifulsoup4 4.13.5.
