# GP Tour — rozszerzenie strukturalnych wyników Tenis NET (T-027)

**Decyzja architektoniczna, 13 listopada 2026 r.** Nadal działa **jeden kolektor** w `czerjac/kalendarz`. News Tenis NET i przyszły ranking GP Tour korzystają z tego samego `data/wyniki_news/stan.json`. Dopisujemy **opcjonalne dowody źródłowe**, a nie zastępujemy dotychczasowych pól. Powód: chronimy istniejące newsy i nie powielamy scrapera.

## Co zostało dodane

`ranking_evidence` w jednym wyniku źródłowym:

- `schema_version: 1`;
- `klasyfikacje_zrodla`: wykazy dostarczone przez konkretne źródło, z odrębnymi identyfikatorami/etykietami konkurencji i statusem `DANE_ZRODLOWE_NIEZWERYFIKOWANE`.

**Kluby.org:** `wiersze` to bezpośrednie odczytane przez istniejący parser `/kolejnosc` rekordy `{pozycja, zawodnicy, miejsce, etap}`, osobno dla każdego linku kategorii. Nie przypisujemy im automatycznie rankingu GP Tour ani nie deklarujemy, że zawierają wszystkie miejsca.

**PZT TOP:** obecny parser rozpoznaje tylko miejsca **1 i 2** ze strony `TournamentTabResults.aspx`. Pola `wiersze` zawierają je ze znacznikiem `zakres: TYLKO_MIEJSCA_1_2`. Nie wolno z nich wyciągać wniosku o wszystkich pozostałych miejscach, ani traktować identyfikatorów `pzt-nazwa:...` jako pewnego ID zawodnika.

**Kluby.org / mecze:** `ranking_oznaczenia_wyniku` to jedynie wykryte wyrażenia z oryginalnego pola `wynik`: `tekst_walkower`, `tekst_krecz_ret`. To NIE jest potwierdzony fakt wyjścia na kort ani przyznania zwycięstwa na korcie. Stare pole `walkower`, nawet gdy dotyczy kreczu, nie zostało zmienione, aby nie zepsuć dotychczasowego działania newsów.

## Co wynika z audytu istniejącego archiwum

W archiwum `stan.json` przeanalizowanym **13.11.2026**, bez ujawniania nazwisk:

| Źródło | Turnieje | Mecze | Gotowe do newsów | Bez meczów |
| --- | ---: | ---: | ---: | ---: |
| PLT | 216 | 4232 | 210 | 1 |
| Cuply | 21 | 547 | 16 | 0 |
| Kluby.org | 169 | 2589 | 63 | 48 |
| PZT TOP | 55 | 1806 | 4 | 11 |
| **Łącznie** | **461** | **9174** | **293** | **60** |

Dodatkowo: **8759 meczów** oznaczono jako zakończone, **434** mają dawną flagę walkoweru (w Kluby.org obejmuje ona również sygnały kreczu); **4236 wystąpień graczy w meczach PZT TOP** opiera się na identyfikatorach zastępczych z nazwiska. To LICZBA WYSTĄPIEŃ, nie liczba unikalnych osób. W obrębie Kluby.org wykryto **13** wielokategoriowych turniejów, w PZT TOP **26**.

**Żaden z tych liczników nie oznacza liczby turniejów gotowych do oficjalnego rankingu**. Gotowość wymaga pełnej, zaakceptowanej klasyfikacji, prawidłowo zidentyfikowanych zawodników i potwierdzonych okoliczności udziału w grze.

## Operacje i testy

```bash
# Czyta istniejący archiwalny plik, nie pobiera stron i nie zapisuje danych:
python -m wyniki_news.ranking_audit

# Wszystkie testy parserów wyników na fikcyjnych danych:
python -m unittest discover -s tests/wyniki_news -v
```

Osobny workflow `ranking-evidence-audit.yml` uruchamia testy Python i PHP oraz raport zagregowany. Nie uruchamia produkcyjnego `wyniki_news.build`, nie publikuje WordPressa i nie modyfikuje `main`.

**Ograniczenie:** historyczny `stan.json` nie zawiera nowych pól `ranking_evidence`. Zostaną one wygenerowane dopiero przez kolejne udane odczyty zmodyfikowanego kodu, po review i scaleniu PR. Nie uruchamiamy masowego backfillu historycznych turniejów przed odbiorem i osobną oceną ryzyka/zakresu.

**Następne zadanie TenisOne:** interpretować nowe `ranking_evidence` jako **propozycje do weryfikacji**, nie automatyczne `EventPlacement` i punkty. Zachować źródłową wersję `SourceRecord`, rozpoznać identyfikatory pewne/zastępcze, oddzielić wydarzenie sportowe od rankingu GP Tour, nie poprawiać punktów bez decyzji Fundacji.
