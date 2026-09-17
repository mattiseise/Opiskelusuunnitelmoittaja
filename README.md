# Opiskelusuunnitelmoittaja

Täyttää opiskelusuunnitelmalomakkeen selaimessa Excel-taulukosta rivi kerrallaan, jotta samaa
taulukkoa ei tarvitse naputella käsin joka opiskelijalle. Työkalu kytkeytyy sinun omaan, jo
kirjautuneeseen Chromeesi (Playwright + Chrome DevTools Protocol), joten kirjautumisia tai
salasanoja ei tarvitse antaa skriptille.

Versio 2 on kirjoitettu uusiksi: Selenium ja webdriver-manager on korvattu Playwrightilla,
pandas openpyxl:llä, ja projekti käyttää `pyproject.toml`-määrittelyä ja `uv`-työkalua.
Toimii macOS:llä, Windowsilla ja Linuxilla. Versiossa 2.1 on graafinen käyttöliittymä ja
valmiit sovelluspaketit.

## Valmis sovellus (suositus)

Lataa uusin paketti [Releases-sivulta](https://github.com/mattiseise/Opiskelusuunnitelmoittaja/releases):
macOS:lle `.dmg` (Apple Silicon), Windowsille `.zip`. Sovellus tarvitsee koneelta vain
Google Chromen; Python tai uv ei ole tarpeen.

Ensimmäisellä käynnistyksellä sovellus kopioi `config.json`-asetukset ja `Opintosuunnitelmat.xlsx`-
pohjan käyttäjän omaan kansioon (macOS: `~/Library/Application Support/Opiskelusuunnitelmoittaja`,
Windows: `%APPDATA%\Opiskelusuunnitelmoittaja`). Tiedosto → *Avaa asetuskansio* vie sinne.

Käyttö ikkunassa:

1. **Käynnistä Chrome** -nappi avaa Chromen erilliseen profiiliin. Pallo muuttuu vihreäksi,
   kun yhteys on kunnossa.
2. Avaa Wilman opiskelusuunnitelmalomake siihen Chrome-ikkunaan.
3. Valitse pääsuuntaus ja rastita lisävalinnat (lukio, YTO, väylä) tai valitse välilehdet käsin.
   Esikatselu näyttää täsmälleen ne rivit, jotka lomakkeelle menevät.
4. **Täytä lomake**. Eteneminen ja loki näkyvät ikkunassa; *Keskeytä* pysäyttää rivin jälkeen.
5. Tarkista rivit Wilmassa ja paina *Tallenna tiedot* (sovellus ei tallenna puolestasi).

Kysymykset, Excel-otsikot, lomakkeen valitsimet ja Chromen portti muokataan *Asetukset…*-ikkunassa.

Paketit on allekirjoitettu ad hoc, ei Applen notarisointia. Jos macOS estää avauksen,
valitse Järjestelmäasetukset → Tietosuoja ja suojaus → *Avaa silti*, tai aja
`xattr -dr com.apple.quarantine /Applications/Opiskelusuunnitelmoittaja.app`. Windowsin
SmartScreen: *Lisätietoja* → *Suorita silti*.

## Komentorivi ja kehitys

### Vaatimukset

- Python 3.12 tai uudempi
- [uv](https://docs.astral.sh/uv/) (`brew install uv` tai `pipx install uv`)
- Google Chrome

### Asennus

```bash
git clone https://github.com/mattiseise/Opiskelusuunnitelmoittaja
cd Opiskelusuunnitelmoittaja
uv sync
```

`uv sync` luo virtuaaliympäristön `.venv/` ja asentaa riippuvuudet. Komennot ajetaan
`uv run suunnitelmoittaja ...` -muodossa (tai aktivoi `.venv` ja jätä `uv run` pois).
GUI kehitysympäristöstä: `uv sync --extra gui && uv run suunnitelmoittaja-gui`.

### Käyttö komentoriviltä

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
uv run suunnitelmoittaja fill            # ohjattu kysely (pääsuuntaus, lukio, YTO, väylä)
uv run suunnitelmoittaja fill 2 --dry-run   # näytä mitä täytettäisiin, älä koske selaimeen
```

Työkalu etsii avoimista välilehdistä sen, jolla lomaketaulukko on. Jos taulukossa on valmiina
tyhjä rivi (Wilmassa on), ensimmäinen Excel-rivi täytetään siihen; loput rivit lisätään
lisäysnapilla. Sivun muihin taulukoihin (esim. Pvm & päivittäjä) ei kosketa. Välilehtien väliin lisätään tyhjä välirivi
(`--no-separator` poistaa sen). Lopuksi tulostuu yhteenveto; virheet kirjataan lokiin
`logs/app.log`. Lisää `-v` nähdäksesi etenemislokin konsolissa, `--debug` yksityiskohdat.

### Ohjattu kysely

`fill` ilman välilehtiä kysyy, mitä opiskelijalle laitetaan: ensin pääsuuntaus
(Ohjelmistokehittäjä / Kyber / IT-tuki), sitten kyllä/ei-kysymyksinä kaksoistutkinto (Lukio),
YTO-opinnot (oletus kyllä) ja väyläopinnot. Tyhjä vastaus valitsee hakasulkeissa isolla
merkityn oletuksen. Kysymykset ja välilehdet määritellään `config.json`-tiedoston
`wizard`-osiossa:

```jsonc
"wizard": {
  "main_question": "Mikä on opiskelijan pääsuuntaus?",
  "main_sheets": ["Ohjelmistokehittäjä", "Kyber", "IT-tuki"],
  "optional_sheets": [
    { "sheet": "Lukio", "question": "Onko opiskelija kaksoistutkinnossa (lukio)?", "default": false },
    { "sheet": "YTO",   "question": "Lisätäänkö YTO-opinnot?",                     "default": true },
    { "sheet": "Väylä", "question": "Lisätäänkö väyläopinnot?",                    "default": false }
  ]
}
```

Jos `wizard`-osiota ei ole, `fill` kysyy välilehdet numeroina kuten aiemmin.

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
uv sync --extra gui                      # asentaa myös dev-riippuvuudet ja PySide6
uv run playwright install chromium       # testien selain (kerran)
uv run pytest                            # 51 testiä: selaintestit + GUI offscreen
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

### Sovelluspaketin rakentaminen

```bash
scripts/build.sh                                           # macOS → dist/*.app + .dmg (Linux → .tar.gz)
powershell -ExecutionPolicy Bypass -File scripts\build.ps1  # Windows → dist/*.zip
```

Paketointi käyttää PyInstalleria (`packaging/Opiskelusuunnitelmoittaja.spec`). Playwrightin
Node-ajuri pakataan mukaan, selainta ei: sovellus kytkeytyy käyttäjän omaan Chromeen.
Paketoitua sovellusta voi ajaa myös komentoriviltä: `Opiskelusuunnitelmoittaja --cli fill 1`.

Julkaisu: `git tag v2.1.0 && git push --tags` käynnistää GitHub Actions -putken
(`.github/workflows/release.yml`), joka ajaa testit, rakentaa macOS- ja Windows-paketit ja
liittää ne GitHub Releaseen.

Lomaketestit ajetaan oikealla Chromiumilla paikallista testilomaketta
(`tests/fixtures/lomake.html`) vastaan. Valmiiksi asennetun selaimen voi osoittaa
ympäristömuuttujalla `SUUNNITELMOITTAJA_CHROMIUM=/polku/chromium`.

Rakenne:

```
src/opiskelusuunnitelmoittaja/
  cli.py        komennot chrome / sheets / fill
  wizard.py     ohjattu kysely (pääsuuntaus, lukio, YTO, väylä)
  paths.py      resurssit paketissa, käyttäjän data-hakemisto
  gui/          PySide6-käyttöliittymä (app, main_window, settings_dialog, worker)
  config.py     asetusten lataus ja oletukset, Chromen tunnistus
  excel.py      Excelin luku (openpyxl), arvojen muotoilu
  browser.py    Chromen käynnistys ja CDP-yhteys
  filler.py     rivien lisäys ja täyttö, uudelleenyritykset, yhteenveto
  logsetup.py   lokitus
```
