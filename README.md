# crm-data-cleanup

![Die Bereinigung als Ablauf: 2.000 eingelesene Zeilen, 190 mit Begründung beiseitegelegt, 484 Dubletten zusammengeführt, 1.326 saubere Kontakte; Prüfungen bestanden und bereit zum Import](docs/images/overview.png)

CRM-Exporte aus verschiedenen Werkzeugen beschreiben dieselbe Person mehrfach: mit unterschiedlich geschriebenen E-Mail-Adressen, Telefonnummern in einem Dutzend Schreibweisen und dazwischen Testeinträgen, internen Adressen und Tastatur-Müll. Unverändert importiert, füllen sie das neue CRM mit Dubletten und unerreichbaren Kontakten; werden sie durch Löschen bereinigt, gehen echte Kontakte verloren.

Dieses Repository zeigt eine Pipeline, die solche Exporte **vor** dem Import bereinigt, dabei keine Zeile löscht und einem Menschen eine Prüfseite zur Freigabe bereitstellt. Python 3.11+, nur Standardbibliothek.

## Die vier Schritte

1. **Einlesen und vereinheitlichen.** Mehrere CSV-Dateien mit unterschiedlichen Spaltennamen werden über eine kleine TOML-Zuordnung je Quelle (`config.example.toml`) gelesen und in eine gemeinsame Form gebracht.
2. **Normalisieren.** Leerzeichen werden zusammengefasst. E-Mail-Adressen werden klein geschrieben und geprüft. Telefonnummern werden nach E.164 umgewandelt, mit Deutschland als Standardland: `0151 0000 1234`, `0151/00001234`, `+49 (0)151 0000 1234` und `0049 151 0000 1234` werden alle zu `+4915100001234`. Eine Nummer braucht 9 bis 15 Ziffern; was nicht eindeutig eine Nummer ist, wird abgelehnt und nicht geraten.
3. **Beiseitelegen, nie löschen.** Zeilen von internen Domains, Testeinträge, Tastatur-Müll (ein Name ohne Vokale: ausgeschlossen ab sechs Buchstaben oder mit einem Tastaturreihen-Muster, kürzere wie `Plch` werden nur markiert) und Zeilen ohne nutzbaren Kontaktweg landen mit Begründung in `excluded.csv`. Grenzfälle bleiben in der Ausgabe, tragen aber `suspect = yes` und den Grund.
4. **Dubletten erkennen und zusammenführen.** Zeilen werden per Union-Find über die normalisierte E-Mail-Adresse **und** Telefonnummer gruppiert, auch über mehrere Ecken: Teilen A und B eine E-Mail-Adresse und B und C eine Telefonnummer, sind alle drei dieselbe Person. Die vollständigste Zeile führt; weitere E-Mail-Adressen und Nummern stehen in `email_2` / `phone_2` (weitere in `more_emails` / `more_phones`), die zusammengeführten Zeilen in `merged_from`. Ausgeschlossene Zeilen werden vor dem Abgleich beiseitegelegt, damit ein Testeintrag nie zwei echte Kontakte verbinden kann.

Danach laufen die Rechenproben als harte Assertions, im Speicher und noch einmal auf den von der Platte zurückgelesenen Dateien. Schlägt eine fehl, bricht der Lauf mit Exit-Code 1 ab:

- Eingangszeilen = ausgeschlossen + in einen anderen Datensatz zusammengeführt + Ausgabedatensätze
- jede Eingangszeile ist genau einmal berücksichtigt
- keine normalisierte E-Mail-Adresse und keine Telefonnummer geht verloren
- jede E-Mail-Adresse, Telefonnummer und ID ist in `clean.csv` eindeutig
- die Formate sind gültig (E-Mail klein geschrieben, Telefonnummer E.164, Datum ISO)

## Schnellstart

```bash
python -m crm_cleanup run --input data/sample/*.csv --out out/
open out/review.html        # unter Linux xdg-open, unter Windows start
python -m unittest          # 73 Tests
```

Die Ausgabe des Laufs mit den Beispieldaten:

```
Eingangszeilen       2.000
Ausgeschlossen         190   -> out/excluded.csv
Zusammengeführt        484
Saubere Kontakte     1.326   -> out/clean.csv
  davon verdächtig     110   -> prüfen in out/review.html
Alle Prüfungen bestanden. Öffnen Sie review.html und geben Sie frei, bevor Sie importieren.
```

![Terminal: Lauf mit den Beispieldaten, Bilanz 2.000 = 190 + 484 + 1.326, alle Prüfungen bestanden, Tests grün](docs/images/cli-run.png)

## Ausgabe

Der Lauf mit den beiden Beispieldateien (`data/sample/`, 2.000 erfundene Zeilen, Seed 42):

| | Zeilen |
|---|---|
| Eingangszeilen | 2.000 |
| ausgeschlossen (`excluded.csv`) | 190 |
| in einen anderen Datensatz zusammengeführt | 484 |
| **Saubere Kontakte (`clean.csv`)** | **1.326** |

`2.000 = 190 + 484 + 1.326`. Die ausgeschlossenen Zeilen verteilen sich auf 60 interne Adressen, 60 Testeinträge, 40 Tastatur-Müll und 30 ohne nutzbaren Kontaktweg. 381 Ausgabedatensätze sind aus mehr als einer Zeile entstanden (278 Paare, 103 Dreiergruppen), und 110 Datensätze tragen die Markierung `suspect`.

| Datei | Inhalt |
|---|---|
| `out/clean.csv` | eine Zeile je Person: `id, name, company, city, email, email_2, more_emails, phone, phone_2, more_phones, created, sources, merged_from, suspect, suspect_reasons, notes` |
| `out/excluded.csv` | jede beiseitegelegte Zeile mit ihren Originalwerten und dem Grund |
| `out/review.html` | Seite für die Prüfung durch einen Menschen: ausgeschlossene Zeilen nach Grund, verdächtige Datensätze, die größten Zusammenführungsgruppen, Suchfeld |
| `out/report.md` | die Bilanz von oben sowie Zahlen je Grund, Markierung und Gruppengröße |

Eine Zusammenführung aus den Beispieldaten: Drei Zeilen aus zwei Exporten werden zu einem Datensatz:

```
crm_export_a  A-00172  Philipp Jung    pjung@example.com             +49 151 0000 9107    Ulm
crm_export_b  B-00904  Philipp / Jung  philipp.jung@example.com      0049 151 0000 9107   Ulm
crm_export_a  A-00016  Philipp Jung    Pjung@Example.Com             (kein Telefon)       Ulm

-> crm_export_a:A-00172  Philipp Jung  pjung@example.com  philipp.jung@example.com  +4915100009107
   merged_from: crm_export_b:B-00904 | crm_export_a:A-00016
```

Werte, die sich nicht normalisieren lassen (eine E-Mail-Adresse wie `n/a`, ein Datum wie `31.02.2024`), gehen nicht verloren: Sie stehen in der Spalte `notes`.

## Warum nichts gelöscht wird

Eine Bereinigung, die löscht, lässt sich nicht nachprüfen. Alles, was die Pipeline beiseitelegt, bleibt mit den Originalwerten und der ausgelösten Regel in `excluded.csv`, und jede zusammengeführte Zeile bleibt über `merged_from` nachvollziehbar. Ist eine Regel zu streng, ist die Zeile mit einer Suche gefunden und lässt sich zurückholen.

## Warum ein Mensch vor dem Import freigibt

Die Regeln sind Faustregeln. Ein Sammelpostfach wie `info@` verbindet Personen, die nicht dieselben sind, und ein Name mit wenigen Vokalen kann ein echter Name sein. `review.html` legt die Fälle, in denen das passieren kann, einem Menschen vor: alle ausgeschlossenen Zeilen, alle verdächtigen Datensätze und die größten Zusammenführungsgruppen. Importiert wird nach dieser Prüfung, nicht davor.

![Prüfseite: Kennzahlen, Freigabe-Checkliste, ausgeschlossene Zeilen nach Grund gruppiert, verdächtige Datensätze mit dem Grund ihrer Markierung](docs/images/review-page.png)

## Mit eigenen Daten

Kopieren Sie `config.example.toml`, tragen Sie Ihre internen Domains ein und ordnen Sie die Spalten jedes Exports zu (`name` oder `first_name` und `last_name`; `email`, `email_2`, `phone`, `phone_2`, `company`, `city`, `created`). Legen Sie die Dateien in `data/real/` ab (von Git ignoriert) und starten Sie den Lauf mit `--config`:

```bash
python -m crm_cleanup run --input data/real/*.csv --out out/ --config meine-config.toml
```

Auch `out/` wird von Git ignoriert, weil es Kontaktdaten enthält. Wenn Sie `clean.csv` in einer Tabellenkalkulation öffnen, importieren Sie sie als Text: Tabellenkalkulationen machen aus `+4915100001234` eine Zahl und verlieren das Pluszeichen.

## Beispieldaten

```bash
python -m crm_cleanup.generate --n 2000 --seed 42 --out data/sample/
```

Der Generator schreibt zwei Dateien mit unterschiedlichen Spaltennamen und ausschließlich erfundenen Daten: Adressen auf example.com / example.org, ausgedachte Namen, Telefonnummern im Bereich +49 151 0000xxxx. Derselbe Seed liefert byteidentische Dateien. Er kennt außerdem die Wahrheit (wie viele Zeilen Ausschuss sind, wie viele Personen doppelt vorkommen), und ein Test prüft die Pipeline dagegen: Auf den Beispieldaten findet sie genau die 190 Ausschusszeilen und führt genau die 484 eingebauten Dubletten zusammen. Das zeigt, dass die Mechanik funktioniert. Es misst nicht, wie gut die Ausschlussregeln zu Ihren echten Daten passen.

## Bekannte Grenzen

- **Namen.** Ein Name, der komplett in Großbuchstaben oder komplett klein geschrieben ist, wird mit `title()` normalisiert: Aus `MCDONALD` wird `Mcdonald`, und nur eine kurze Liste von Namenszusätzen (`von`, `van`, `de` ...) bleibt klein. Namen in gemischter Schreibweise werden nie angefasst.
- **Schwellenwerte.** Die Schwellen für Verdacht und Ausschluss (Vokalanteil 10 % und 15 %, sechs Buchstaben, die Liste der Tastaturreihen) sind an den erzeugten Beispieldaten kalibriert. Bei echten Daten, in anderen Sprachen oder mit anderen Namensgewohnheiten sind Fehlalarme und Lücken zu erwarten; dafür gibt es die Prüfseite.
- **Abgleich.** Nur exakte Treffer bei E-Mail-Adresse und Telefonnummer verbinden Zeilen. Einen unscharfen Namensabgleich gibt es nicht, und ein Sammelpostfach verbindet Personen, die nicht dieselben sind.
- **Telefonnummern.** `049 151 ...` wird nur dann als Landesvorwahl 49 gelesen, wenn ein Trennzeichen folgt, weil `04921 ...` (Emden) eine nationale Nummer ist. Ziffernfolgen, die mit `49` beginnen und mindestens zehn Ziffern haben, gelten als international.
- **IDs.** Eine ID oder ein Quelldateiname mit `|` wird abgelehnt, weil `|` in den Ausgabedateien die Listen trennt.

## Aufbau

```
crm_cleanup/   normalize.py  rules.py  dedupe.py  checks.py  pipeline.py  outputs.py  config.py  cli.py  generate.py
config.example.toml
data/sample/   zwei erzeugte Exporte
tests/         python -m unittest
```

## Lizenz

MIT, siehe `LICENSE`.

## In English

This project cleans CRM contact exports before they are imported into a new system; console output, reports and the review page are in German. Several CSV files with different column names are unified, e-mails and phone numbers are normalised, and duplicates are merged through shared e-mails or phone numbers, even across several hops. Internal addresses, test entries, keyboard junk and rows without a contact method are never deleted but listed with a reason in `excluded.csv`. Hard integrity checks stop the run if any row, e-mail or phone number would be lost. A person reviews `review.html` before the import, because the rules are rules of thumb and, for example, a shared mailbox can join different people.
