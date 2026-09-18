# Opintosuunnitelman täyttäjä

(Repo ja Python-paketti: `Opiskelusuunnitelmoittaja` / `opiskelusuunnitelmoittaja`; komentorivikomento `suunnitelmoittaja`.)

Täyttää opiskelusuunnitelmalomakkeen selaimessa Excel-taulukosta rivi kerrallaan, jotta samaa
taulukkoa ei tarvitse naputella käsin joka opiskelijalle. Työkalu kytkeytyy sinun omaan, jo
kirjautuneeseen Chromeesi (Playwright + Chrome DevTools Protocol), joten kirjautumisia tai
salasanoja ei tarvitse antaa skriptille.

Versio 2 on kirjoitettu uusiksi: Selenium ja webdriver-manager on korvattu Playwrightilla,
pandas openpyxl:llä, ja projekti käyttää `pyproject.toml`-määrittelyä ja `uv`-työkalua.
Toimii macOS:llä, Windowsilla ja Linuxilla. Versiossa 2.1 on graafinen käyttöliittymä ja
valmiit sovelluspaketit.

## Pikaohjeet alustoittain

Sovellus tarvitsee koneelta Google Chromen. Kaikki muu (Python, Playwright-ajuri, fontit)
tulee paketin mukana. Pakettien latauspaikka: [Releases](https://github.com/mattiseise/Opiskelusuunnitelmoittaja/releases).

### macOS

**Valmis sovellus**

1. Lataa `OpintosuunnitelmanTayttaja-<versio>-macos-arm64.dmg`, avaa se ja vedä
   *Opintosuunnitelman täyttäjä* Ohjelmat-kansioon.
2. Ensimmäisellä avauksella macOS voi estää ad hoc -allekirjoitetun paketin. Salli se joko
   Järjestelmäasetukset → Tietosuoja ja suojaus → *Avaa silti*, tai Terminaalissa:

   ```bash
   xattr -dr com.apple.quarantine "/Applications/Opintosuunnitelman täyttäjä.app"
   ```

3. Käynnistä sovellus Launchpadista tai Spotlightista ("Opintosuunnitelman täyttäjä").

Asetukset ja Excel-pohja kopioidaan ensimmäisellä käynnistyksellä kansioon
`~/Library/Application Support/OpintosuunnitelmanTayttaja/` (Tiedosto → *Avaa asetuskansio*).

**Kehitysversio lähdekoodista** (Homebrew ja uv):

```bash
brew install uv
git clone https://github.com/mattiseise/Opiskelusuunnitelmoittaja
cd Opiskelusuunnitelmoittaja
uv sync --extra gui
uv run suunnitelmoittaja-gui           # käyttöliittymä
scripts/make-launcher.sh --dock        # Dock-käynnistin "Opintosuunnitelman täyttäjä (dev)"
```

**Oma paketti** (.app + .dmg kansioon `dist/`):

```bash
scripts/build.sh
```

**Komentorivi** (samasta kansiosta):

```bash
uv run suunnitelmoittaja chrome        # käynnistä Chrome, avaa lomake siihen ikkunaan
uv run suunnitelmoittaja fill          # ohjattu kysely: pääsuuntaus, lukio, YTO, väylä
uv run suunnitelmoittaja fill 1,3      # tai välilehdet suoraan
uv run suunnitelmoittaja fill 2 --dry-run
```

Paketoidusta sovelluksesta komentorivi on
`"/Applications/Opintosuunnitelman täyttäjä.app/Contents/MacOS/OpintosuunnitelmanTayttaja" --cli fill 1`.

### Windows

**Valmis sovellus**

1. Lataa `OpintosuunnitelmanTayttaja-<versio>-windows-x64.zip` ja pura se esimerkiksi kansioon
   `C:\Ohjelmat\OpintosuunnitelmanTayttaja\`.
2. Käynnistä `OpintosuunnitelmanTayttaja.exe`. SmartScreen varoittaa tuntemattomasta julkaisijasta:
   *Lisätietoja* → *Suorita silti*.
3. Pikakuvake työpöydälle tai tehtäväpalkkiin: hiiren oikea → *Lähetä kohteeseen* → *Työpöytä*,
   tai vedä käynnissä olevan sovelluksen kuvake tehtäväpalkkiin ja valitse *Kiinnitä*.

Asetukset ja Excel-pohja kopioidaan ensimmäisellä käynnistyksellä kansioon
`%APPDATA%\OpintosuunnitelmanTayttaja\` (Tiedosto → *Avaa asetuskansio*).

**Kehitysversio lähdekoodista** (PowerShell; uv asennetaan wingetillä):

```powershell
winget install --id astral-sh.uv -e
git clone https://github.com/mattiseise/Opiskelusuunnitelmoittaja
cd Opiskelusuunnitelmoittaja
uv sync --extra gui
uv run suunnitelmoittaja-gui
```

**Oma paketti** (.zip kansioon `dist\`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

**Komentorivi**:

```powershell
uv run suunnitelmoittaja chrome
uv run suunnitelmoittaja fill
uv run suunnitelmoittaja fill 1,3
```

Paketoidusta sovelluksesta: `OpintosuunnitelmanTayttaja.exe --cli fill 1`.

### Julkaisu (molemmat paketit kerralla)

Versiotagi käynnistää GitHub Actions -putken, joka ajaa testit, rakentaa macOS- ja
Windows-paketit ja liittää ne Releaseen asennusohjeineen:

```bash
git tag v2.1.0
git push origin v2.1.0
```

## Käyttö ikkunassa

1. **Käynnistä Chrome** avaa Chromen erilliseen profiiliin, johon kirjautuminen säilyy.
   Tila näkyy tekstinä: burgundi "Yhteys kunnossa · portti 9222", kun yhteys on.
2. Avaa Wilman opiskelusuunnitelmalomake siihen Chrome-ikkunaan.
3. Valitse pääsuuntaus ja rastita lisävalinnat (lukio, YTO, väylä), tai valitse välilehdet käsin.
   Esikatselu näyttää täsmälleen ne rivit, jotka lomakkeelle menevät.
4. Rastita esikatselusta vietävät rivit (oletuksena kaikki; otsikkorivin rasti valitsee tai
   poistaa kaikki kerralla) ja paina **Täytä lomake**. Eteneminen ja loki näkyvät ikkunassa;
   *Keskeytä* pysäyttää rivin jälkeen.
5. Tarkista rivit Wilmassa ja paina *Tallenna tiedot* (sovellus ei tallenna puolestasi).

Kysymykset, Excel-otsikot, lomakkeen valitsimet ja Chromen portti muokataan *Asetukset*-ikkunassa.

Ulkoasu noudattaa BC Helsingin design systemiä (`gui/theme.py`): pergamentti- ja burgunditokenit,
Public Sans ja Source Serif 4 (OFL-lisenssi, fontit pakataan mukaan), ei varjoja, ei
kulmapyöristyksiä, ei ikoneita; erottimina keskipiste, numerot ja hairline-viivat.
Kuvakevaihtoehdot ovat kansiossa `packaging/icon-variants/`.

## Komentorivi tarkemmin

Työkalu etsii avoimista Chromen välilehdistä sen, jolla lomaketaulukko on. Jos taulukossa on
valmiina tyhjä rivi (Wilmassa on), ensimmäinen Excel-rivi täytetään siihen; loput rivit lisätään
lisäysnapilla. Sivun muihin taulukoihin (esim. Pvm & päivittäjä) ei kosketa. Välilehtien väliin
lisätään tyhjä välirivi (`--no-separator` poistaa sen). Lopuksi tulostuu yhteenveto; virheet
kirjataan lokiin `logs/app.log`. `-v` näyttää etenemislokin konsolissa, `--debug` yksityiskohdat,
`uv run suunnitelmoittaja sheets` listaa Excelin välilehdet numeroituina.

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
scripts/build.sh                                           # macOS → dist/Opintosuunnitelman täyttäjä.app + .dmg (Linux → .tar.gz)
powershell -ExecutionPolicy Bypass -File scripts\build.ps1  # Windows → dist/*.zip
```

Paketointi käyttää PyInstalleria (`packaging/OpintosuunnitelmanTayttaja.spec`). Playwrightin
Node-ajuri pakataan mukaan, selainta ei: sovellus kytkeytyy käyttäjän omaan Chromeen.
Paketoitua sovellusta voi ajaa myös komentoriviltä: `OpintosuunnitelmanTayttaja --cli fill 1`.

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
