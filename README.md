# Opiskelusuunnitelmoittaja

Täyttää opiskelusuunnitelmalomakkeen selaimessa Excel-taulukosta rivi kerrallaan, jotta samaa
taulukkoa ei tarvitse naputella käsin joka opiskelijalle. Työkalu kytkeytyy sinun omaan, jo
kirjautuneeseen Chromeesi (Playwright + Chrome DevTools Protocol), joten kirjautumisia tai
salasanoja ei tarvitse antaa skriptille.

Versio 2 on kirjoitettu uusiksi: Selenium ja webdriver-manager on korvattu Playwrightilla,
pandas openpyxl:llä, ja projekti käyttää `pyproject.toml`-määrittelyä ja `uv`-työkalua.
Toimii macOS:llä, Windowsilla ja Linuxilla.

## Vaatimukset

- Python 3.12 tai uudempi
- [uv](https://docs.astral.sh/uv/) (`brew install uv` tai `pipx install uv`)
- Google Chrome

## Asennus

```bash
git clone https://github.com/mattiseise/Opiskelusuunnitelmoittaja
cd Opiskelusuunnitelmoittaja
uv sync
```

`uv sync` luo virtuaaliympäristön `.venv/` ja asentaa riippuvuudet. Komennot ajetaan
`uv run suunnitelmoittaja ...` -muodossa (tai aktivoi `.venv` ja jätä `uv run` pois).

## Käyttö

Kolme askelta:

**1. Käynnistä Chrome etädebuggauksella.**

```bash
uv run suunnitelmoittaja chrome
```

Komento käynnistää Chromen erilliseen profiiliin (`~/.opiskelusuunnitelmoittaja/chrome-profile`)
portti 9222 auki. Erillinen profiili on pakollinen, koska Chrome 136 ja uudemmat eivät salli
etädebuggausta oletusprofiilissa. Kirjautumiset säilyvät profiilissa kertojen välillä, joten
kirjautuminen tarvitsee tehdä vain kerran.

Jos haluat käynnistää Chromen käsin, `uv run suunnitelmoittaja chrome --print` tulostaa
komennon omalle käyttöjärjestelmällesi. macOS:llä se on:

```bash
open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.opiskelusuunnitelmoittaja/chrome-profile"
```

**2. Avaa lomakesivu** siihen Chrome-ikkunaan ja kirjaudu tarvittaessa.

**3. Täytä lomake.**

```bash
uv run suunnitelmoittaja sheets          # listaa Excelin välilehdet
uv run suunnitelmoittaja fill 1,3        # täytä välilehdet 1 ja 3 (numerot tai nimet)
uv run suunnitelmoittaja fill            # kysyy välilehdet
uv run suunnitelmoittaja fill 2 --dry-run   # näytä mitä täytettäisiin, älä koske selaimeen
```

Työkalu etsii avoimista välilehdistä sen, jolla lomaketaulukko on. Jos taulukossa on valmiina
tyhjä rivi (Wilmassa on), ensimmäinen Excel-rivi täytetään siihen; loput rivit lisätään
lisäysnapilla. Sivun muihin taulukoihin (esim. Pvm & päivittäjä) ei kosketa. Välilehtien väliin lisätään tyhjä välirivi
(`--no-separator` poistaa sen). Lopuksi tulostuu yhteenveto; virheet kirjataan lokiin
`logs/app.log`. Lisää `-v` nähdäksesi etenemislokin konsolissa, `--debug` yksityiskohdat.

## Excel-tiedoston rakenne

Jokainen välilehti on yksi suunnitelma. Ensimmäinen rivi on otsikkorivi, ja siltä pitää
löytyä nämä otsikot (kirjainkoko ja ylimääräiset välilyönnit eivät haittaa):

| Otsikko                              | Lomakkeen kenttä  |
| ------------------------------------ | ----------------- |
| `Osaamistavoite`                     | osaamistavoite    |
| `Laajuus`                            | laajuus           |
| `Suoritustapa / osaaminen hankitaan` | suoritustapa      |
| `Suoritusajankohta`                  | suoritusajankohta |

Kokonaan tyhjät rivit ohitetaan. Numerot muotoillaan siististi (`25.0` → `25`), päivämäärät
muotoon `pp.kk.vvvv`. Tyhjä solu täytetään lomakkeelle välilyönnillä, koska lomake ei
hyväksy tyhjää kenttää (muutettavissa asetuksella `empty_value`).

Otsikot voi nimetä toisin `config.json`-tiedoston `excel_columns`-osiossa.

## Asetukset (`config.json`)

Kaikki avaimet ovat valinnaisia; puuttuvat täydennetään oletuksilla.

```jsonc
{
  "files": { "excel_file": "Opintosuunnitelmat.xlsx", "log_file": "logs/app.log" },
  "browser": {
    "remote_debugging_port": 9222,
    "user_data_dir": "",          // tyhjä = ~/.opiskelusuunnitelmoittaja/chrome-profile
    "chrome_path": "",            // tyhjä = tunnistetaan automaattisesti
    "page_url_contains": "",      // esim. "wilma" → valitse välilehti osoitteen perusteella
    "timeout_ms": 10000
  },
  "selectors": {
    "table_body": "table:has(th:has-text(\"Osaamistavoite\")) tbody",  // vain opintotaulukko
    "add_row_button": "[id$='__add']",
    "field_cells": {
      "osaamistavoite": "td:nth-child(1)",
      "laajuus": "td:nth-child(2)",
      "suoritustapa": "td:nth-child(3)",
      "suoritusajankohta": "td:nth-child(4)"
    },
    "input_in_cell": "input, textarea, select"
  },
  "excel_columns": { "osaamistavoite": "Osaamistavoite", "...": "..." },
  "empty_value": " ",
  "separator_row_between_sheets": true,
  "retry": { "max_attempts": 3, "delay_s": 1.0 },
  "logging": { "level": "INFO" }
}
```

Jos lomakkeen rakenne muuttuu, päivitä `selectors`-osio. Playwright hyväksyy CSS-valitsimet
ja `xpath=`-etuliitteiset XPath-lausekkeet. `table_body` kannattaa rajata yhteen taulukkoon
(oletus tunnistaa sen Osaamistavoite-otsikosta); jos valitsin osuu useaan, käytetään
ensimmäistä ja lokiin tulee varoitus. Lisäysnappi haetaan ensin taulukon läheltä, sitten
koko sivulta.

## Vianetsintä

**"Chrome ei vastaa osoitteessa http://127.0.0.1:9222"** – Chrome ei ole käynnissä
etädebuggauksella. Aja `uv run suunnitelmoittaja chrome`. Jos Chrome oli jo auki tavallisena,
sulje se ensin tai anna eri `user_data_dir`.

**"Lomaketta ei löytynyt miltään avoimelta välilehdeltä"** – lomakesivu ei ole auki siinä
Chromessa, joka käynnistettiin etädebuggauksella, tai `selectors.table_body` ei osu.
Aseta `browser.page_url_contains`, jos oikea välilehti pitää valita osoitteen perusteella.

**"Välilehdeltä puuttuvat sarakkeet"** – Excelin otsikkorivi ei vastaa `excel_columns`-asetusta.
Virheilmoitus listaa löydetyt otsikot.

**"rivin lisäys epäonnistui"** – lisäysnapin valitsin `selectors.add_row_button` ei osu.
Tarkista napin `id` selaimen kehittäjätyökaluilla.

## Kehitys

```bash
uv sync                                  # asentaa myös dev-riippuvuudet
uv run playwright install chromium       # testien selain (kerran)
uv run pytest                            # 34 testiä, mukana oikea selaintesti
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

Lomaketestit ajetaan oikealla Chromiumilla paikallista testilomaketta
(`tests/fixtures/lomake.html`) vastaan. Valmiiksi asennetun selaimen voi osoittaa
ympäristömuuttujalla `SUUNNITELMOITTAJA_CHROMIUM=/polku/chromium`.

Rakenne:

```
src/opiskelusuunnitelmoittaja/
  cli.py        komennot chrome / sheets / fill
  config.py     asetusten lataus ja oletukset, Chromen tunnistus
  excel.py      Excelin luku (openpyxl), arvojen muotoilu
  browser.py    Chromen käynnistys ja CDP-yhteys
  filler.py     rivien lisäys ja täyttö, uudelleenyritykset, yhteenveto
  logsetup.py   lokitus
```
