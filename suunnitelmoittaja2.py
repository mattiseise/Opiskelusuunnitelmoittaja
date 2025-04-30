from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import pandas as pd
import time

# HUOM!
# KÄYNNISTÄ ENSIN SELAIN COMMAND PROMPTISSA KOMENNOLLA (Mukaan myös lainausmerkit):
# "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Temp\EdgeProfile"

# Asetetaan Edge käyttämään etäohjausporttia
edge_options = Options()
edge_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

# Liitetään Selenium olemassa olevaan Edge-istuntoon
try:
    driver = webdriver.Edge(service=webdriver.EdgeService(EdgeChromiumDriverManager().install()), options=edge_options)
    print("Yhteys olemassa olevaan Edge-istuntoon muodostettu onnistuneesti.")
except Exception as e:
    print(f"Yhteyden muodostaminen epäonnistui: {e}")

# Tarkistetaan sivun otsikko
if 'driver' in locals():
    title = driver.title
    print(f"Sivuun saatu yhteys. Nykyisen sivun otsikko: {title}")
    
    # Luetaan Excel-tiedosto ja kysytään käyttäjältä, mitkä sheetit täytetään
    try:
        excel_file = 'D:/Programming/Opiskelusuunnitelmoittaja/Opintosuunnitelmat.xlsx'
        xls = pd.ExcelFile(excel_file)
        print("Excel-tiedosto luettu onnistuneesti.")
    except Exception as e:
        print(f"Excel-tiedoston lukeminen epäonnistui: {e}")
        driver.quit()
        exit()
    
    # Tulostetaan saatavilla olevat sheetit
    print("Saatavilla olevat sheetit:")
    for idx, sheet_name in enumerate(xls.sheet_names):
        print(f"{idx + 1}: {sheet_name}")
    
    sheet_indices = input("Syötä niiden sheetien numerot, jotka haluat täyttää, pilkuilla erotettuna: ")
    selected_sheets = [xls.sheet_names[int(i) - 1] for i in sheet_indices.split(',') if i.strip().isdigit()]
    
    # Määritellään taulukon runkon XPath
    table_tbody_xpath = '/html/body/div[2]/div/div/div[2]/div/main/form/div[1]/div/div[2]/div/div/table/tbody'
    
    # Käytetään annettua add-row -napin XPathia
    add_row_button_xpath = '//*[@id="f-prepeater9700__add"]'
    
    # Käydään läpi valitut sheetit
    current_row = 1  # Aloitetaan ensimmäisestä taulukon rivistä
    for sheet_name in selected_sheets:
        print(f"Käsitellään sheet: {sheet_name}")
        df = pd.read_excel(xls, sheet_name=sheet_name)
        
        # Varmistetaan, että lomakkeella on riittävästi rivejä
        required_rows = len(df.index)
        existing_rows = 0  # Oletetaan, että otsikkorivi jätetään väliin

        # Lisätään rivejä niin kauan, että taulukossa on tarpeeksi rivejä
        while existing_rows < required_rows:
            try:
                add_row_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, add_row_button_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", add_row_button)
                ActionChains(driver).move_to_element(add_row_button).perform()
                add_row_button.click()
                print(f"Lisättiin rivi. Rivien määrä nyt: {existing_rows + 1}")
                existing_rows += 1
                time.sleep(1)  # Odotetaan hetki, jotta rivi varmasti luodaan ennen seuraavaa
            except Exception as e:
                print(f"Virhe uuden rivin lisäämisessä: {e}")
                driver.quit()
                exit()
        
        # Täytetään taulukon rivit Excelin datan mukaisesti
        for index, row in df.iterrows():
            try:
                # Oletetaan, että taulukon soluissa on seuraava järjestys:
                # td[1]: osaamistavoite, td[2]: laajuus, td[3]: suoritustapa, td[4]: suoritusajankohta
                row_xpath = f'{table_tbody_xpath}/tr[{current_row}]'
                osaamistavoite_field = driver.find_element(By.XPATH, row_xpath + '/td[1]')
                laajuus_field = driver.find_element(By.XPATH, row_xpath + '/td[2]')
                suoritustapa_field = driver.find_element(By.XPATH, row_xpath + '/td[3]')
                suoritusajankohta_field = driver.find_element(By.XPATH, row_xpath + '/td[4]')
                
                # Oletuksena kentissä on <input>-elementit, joten haetaan ne:
                osaamistavoite_input = osaamistavoite_field.find_element(By.TAG_NAME, 'input')
                laajuus_input = laajuus_field.find_element(By.TAG_NAME, 'input')
                suoritustapa_input = suoritustapa_field.find_element(By.TAG_NAME, 'input')
                suoritusajankohta_input = suoritusajankohta_field.find_element(By.TAG_NAME, 'input')
                
                osaamistavoite_input.clear()
                laajuus_input.clear()
                suoritustapa_input.clear()
                suoritusajankohta_input.clear()
                
                osaamistavoite_input.send_keys(row['Osaamistavoite'] if pd.notna(row['Osaamistavoite']) else ' ')
                laajuus_input.send_keys(str(row['Laajuus']) if pd.notna(row['Laajuus']) else ' ')
                suoritustapa_input.send_keys(row['Suoritustapa / osaaminen hankitaan'] if pd.notna(row['Suoritustapa / osaaminen hankitaan']) else ' ')
                suoritusajankohta_input.send_keys(row['Suoritusajankohta'] if pd.notna(row['Suoritusajankohta']) else ' ')
                print(f"Sheet {sheet_name}, rivi {index + 1} täytetty onnistuneesti.")
                current_row += 1
            except Exception as e:
                print(f"Virhe sheetin {sheet_name}, rivin {index + 1} täyttämisessä: {e}")
        
        # Lisätään tyhjä rivi sheetien tietojen väliin
        try:
            add_row_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, add_row_button_xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", add_row_button)
            ActionChains(driver).move_to_element(add_row_button).perform()
            add_row_button.click()
            print(f"Tyhjä rivi lisätty sheetin {sheet_name} jälkeen.")
            current_row += 1
        except Exception as e:
            print(f"Virhe tyhjän rivin lisäämisessä sheetin {sheet_name} jälkeen: {e}")
    
    driver.quit()
else:
    print("Driveria ei voitu alustaa, joten sivun otsikkoa ei voitu tarkistaa.")
