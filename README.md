# Opiskelusuunnitelmoittaja

Tämä projekti automatisoi opiskelusuunnitelmien syöttämisen Wilma-järjestelmään käyttäen Seleniumia.

## Ympäristövaatimukset
- Python 3.8+
- Selenium ja muut riippuvuudet (asennus `pip install -r requirements.txt` tai `pip install selenium webdriver-manager pandas`)
- Microsoft Edge -selain

## Käyttö Windowsissa
1. Varmista, että Edge on asennettu oletuspolkuun `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
2. Avaa komentorivi ja käynnistä Edge etäohjaustilassa:
   ```cmd
   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Temp\EdgeProfile"
   ```
3. Suorita scripti komennolla `python suunnitelmoittaja.py` (tai `suunnitelmoittaja2.py`).
4. Valitse avattavasta Excelistä täytettävät sheetit.

## Käyttö macOS:ssä
1. Varmista, että Edge on asennettu polkuun `/Applications/Microsoft Edge.app`.
2. Avaa terminaali ja käynnistä Edge etäohjaustilassa:
   ```bash
   "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" --remote-debugging-port=9222 --user-data-dir="/tmp/EdgeProfile"
   ```
3. Suorita scripti komennolla `python3 suunnitelmoittaja.py` (tai `suunnitelmoittaja2.py`).
4. Valitse avattavasta Excelistä täytettävät sheetit.

## Yleistä
- Excel-tiedosto `Opintosuunnitelmat.xlsx` luetaan automaattisesti tästä hakemistosta.
- Selain avataan automaattisesti etäohjaustilaan scriptin käynnistyessä, jos se löytyy oletuspoluista.
