Tenis NET – Kalendarz turniejów amatorskich
============================================

Wersja: 0.1.0

Instalacja
----------
1. WordPress → Wtyczki → Dodaj nową → Wyślij wtyczkę na serwer.
2. Wybierz plik ZIP tej wtyczki i kliknij „Zainstaluj teraz”.
3. Włącz wtyczkę.
4. Utwórz zwykłą stronę testową WordPress.
5. W treści strony wpisz shortcode:

   [tenis_kalendarz]

6. Opublikuj stronę i sprawdź kalendarz na komputerze oraz telefonie.

Ustawienia
----------
WordPress → Ustawienia → Kalendarz Tenis NET

Domyślne źródło danych:
https://raw.githubusercontent.com/czerjac/kalendarz/main/data/turnieje.json

Wtyczka buforuje dane przez 15 minut i zachowuje ostatnią poprawną kopię na wypadek chwilowej niedostępności GitHuba.

Wersja 0.1.0 – zakres MVP
------------------------
- pobieranie wspólnego turnieje.json,
- wyszukiwarka,
- filtr: termin,
- filtr: województwo,
- filtr: organizacja,
- filtr: cykl,
- filtr: singiel/debel/mikst,
- tabela na komputerach,
- karty na telefonach,
- rozwijane szczegóły,
- link do zapisów / strony źródłowej,
- licznik widocznych turniejów,
- informacja o dacie aktualizacji danych,
- fallback do ostatniej poprawnej kopii JSON.
