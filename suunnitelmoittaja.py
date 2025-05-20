from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import pandas as pd
import time
import os
import platform
import subprocess
from pathlib import Path

# HUOM!
# Katso README.md käyttöohjeisiin.
# Käynnistä ensin selain etäohjaustilassa. Windowsissa komento on:
# "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Temp\EdgeProfile"
# MacOS:ssa komento on:
# "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" --remote-debugging-port=9222 --user-data-dir="/tmp/EdgeProfile"
# Mikäli remote‑debugging sessio ei ole oikein auki, tämä antaa virheen, että XPATH '//*[@id="f-prepeater9700__add"]' ei ole olemassa tai se on muuttunut. Vika ei ole oikeasti siinä, vaan siinä, että viitataan väärään selainistuntoon.


def launch_edge_remote(port: int = 9222) -> None:
    """Käynnistää Microsoft Edgen remote-debugging -tilassa, jos se löytyy."""
    system = platform.system()
    if system == "Windows":
        edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        profile_dir = Path(r"C:\Temp\EdgeProfile")
    elif system == "Darwin":
        edge_path = Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
        profile_dir = Path("/tmp/EdgeProfile")
    else:
        print("Edgeä ei tueta automaattisesti tällä käyttöjärjestelmällä. Käynnistä selain käsin.")
        return

    if not edge_path.exists():
        print(f"Edgeä ei löytynyt polusta {edge_path}. Käynnistä selain käsin.")
        return

    args = [str(edge_path), f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}"]
    subprocess.Popen(args)
    time.sleep(2)  # Odotetaan hetki, että selain ehtii käynnistyä


# Asetetaan Edge käyttämään etäohjausporttia
launch_edge_remote()
edge_options = Options()
edge_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

# Liitetään Selenium olemassa olevaan Edge-istuntoon
try:
    driver = webdriver.Edge(service=webdriver.EdgeService(EdgeChromiumDriverManager().install()), options=edge_options)
    print("Yhteys olemassa olevaan Edge-istuntoon muodostettu onnistuneesti.")
except Exception as e:
    print(f"Yhteyden muodostaminen epäonnistui: {e}")

# Esimerkki toiminnallisuudesta: Tarkistetaan sivun otsikko
if 'driver' in locals():
    title = driver.title
    print(f"Sivuun saatu yhteys. Nykyisen sivun otsikko: {title}")
    
    # Luetaan Excel-tiedosto ja kysytään käyttäjältä, mitkä sheetit täytetään
    try:
        excel_file = Path(__file__).resolve().parent / 'Opintosuunnitelmat.xlsx'
        xls = pd.ExcelFile(excel_file)
        print(f"Excel-tiedosto {excel_file} luettu onnistuneesti.")
    except Exception as e:
        print(f"Excel-tiedoston lukeminen epäonnistui: {e}")
        driver.quit()
        exit()
    
    # Tulostetaan kaikki sheetit ja kysytään käyttäjältä, mitkä halutaan täyttää
    print("Saatavilla olevat sheetit:")
    for idx, sheet_name in enumerate(xls.sheet_names):
        print(f"{idx + 1}: {sheet_name}")
    
    sheet_indices = input("Syötä niiden sheetien numerot, jotka haluat täyttää, pilkuilla erotettuna: ")
    selected_sheets = [xls.sheet_names[int(i) - 1] for i in sheet_indices.split(',') if i.strip().isdigit()]
    
    # Käydään läpi valitut sheetit
    current_row = 1  # Aloitetaan ensimmäisestä rivistä
    for sheet_name in selected_sheets:
        print(f"Käsitellään sheet: {sheet_name}")
        df = pd.read_excel(xls, sheet_name=sheet_name)
        
        # Varmistetaan, että Wilma-lomakkeella on riittävästi rivejä
        required_rows = len(df.index)  # Tarvittava määrä rivejä
        existing_rows = 0  # Aloitetaan nollasta, koska ensimmäinen rivi on otsikko

        while existing_rows < required_rows:
            try:
                add_row_button = driver.find_element(By.XPATH, '//*[@id="f-prepeater9700__add"]')
                driver.execute_script("arguments[0].scrollIntoView(true);", add_row_button)
                ActionChains(driver).move_to_element(add_row_button).perform()
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="f-prepeater9700__add"]'))).click()
                print(f"Lisättiin rivi. Rivien määrä nyt: {existing_rows + 1}")
                existing_rows += 1
                time.sleep(1)  # Odotetaan hetki, jotta rivi varmasti luodaan ennen seuraavaa toimintoa
            except Exception as e:
                print(f"Virhe uuden rivin lisäämisessä: {e}")
                driver.quit()
                exit()
        
        # Täytetään lomake Wilma-sivulla jokaisen rivin osalta (otsikkorivi jätetään väliin)
        for index, row in df.iterrows():  # Aloitetaan toisesta rivistä, eli datarivistä
            try:
                # Käytetään dynaamisia XPatheja täyttämään oikeat rivit
                osaamistavoite_field = driver.find_element(By.XPATH, f'//*[@id="f-prepeater9700-{current_row}-pfield9700"]')
                laajuus_field = driver.find_element(By.XPATH, f'//*[@id="f-prepeater9700-{current_row}-pfield9704"]')
                suoritustapa_field = driver.find_element(By.XPATH, f'//*[@id="f-prepeater9700-{current_row}-pfield9792"]')
                suoritusajankohta_field = driver.find_element(By.XPATH, f'//*[@id="f-prepeater9700-{current_row}-pfield9703"]')
                
                # Tyhjennetään kentät ennen täyttämistä
                osaamistavoite_field.clear()
                laajuus_field.clear()
                suoritustapa_field.clear()
                suoritusajankohta_field.clear()
                
                # Syötetään tiedot kenttiin
                osaamistavoite_field.send_keys(row['Osaamistavoite'] if pd.notna(row['Osaamistavoite']) else ' ')
                laajuus_field.send_keys(str(row['Laajuus']) if pd.notna(row['Laajuus']) else ' ')
                suoritustapa_field.send_keys(row['Suoritustapa / osaaminen hankitaan'] if pd.notna(row['Suoritustapa / osaaminen hankitaan']) else ' ')
                suoritusajankohta_field.send_keys(row['Suoritusajankohta'] if pd.notna(row['Suoritusajankohta']) else ' ')
                print(f"Sheet {sheet_name}, rivi {index + 1} täytetty onnistuneesti.")
                current_row += 1
            except Exception as e:
                print(f"Virhe sheetin {sheet_name}, rivin {index + 1} täyttämisessä: {e}")
        
        # Lisätään tyhjä rivi eri sheetien tietojen väliin
        try:
            add_row_button = driver.find_element(By.XPATH, '//*[@id="f-prepeater9700__add"]')
            driver.execute_script("arguments[0].scrollIntoView(true);", add_row_button)
            ActionChains(driver).move_to_element(add_row_button).perform()
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="f-prepeater9700__add"]'))).click()
            print(f"Tyhjä rivi lisätty sheetin {sheet_name} jälkeen.")
            current_row += 1
        except Exception as e:
            print(f"Virhe tyhjän rivin lisäämisessä sheetin {sheet_name} jälkeen: {e}")
    
    # Muista sulkea selain yhteyden lopussa
    driver.quit()
else:
    print("Driveria ei voitu alustaa, joten sivun otsikkoa ei voitu tarkistaa.")
