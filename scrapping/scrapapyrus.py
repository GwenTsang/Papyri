from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import time
import random
import sys
import copy

# --- 1. FONCTIONS UTILITAIRES ET NETTOYAGE ---

def get_text_clean(soup_element, label_to_remove):
    """
    Nettoie le texte d'un élément HTML (enlève tooltips, label, espaces).
    """
    if not soup_element:
        return None
    
    # Copie pour ne pas altérer le soup original
    temp_elem = copy.copy(soup_element)
    
    # Suppression des tooltips
    for tooltip in temp_elem.select(".tooltiptext"):
        tooltip.decompose()
    
    full_text = temp_elem.get_text(" ", strip=True)
    # On retire le label et les séparateurs
    clean_text = full_text.replace(label_to_remove, "", 1).strip(" :\u00A0")
    
    return clean_text if clean_text else None

# --- 2. FONCTIONS D'EXTRACTION ---

def extract_field(soup, label_str):
    """
    Récupère une métadonnée simple (Date, Provenance, Material, Language, Content).
    """
    label_str_colon = label_str + ":"
    
    # Stratégie A : Bloc standard .division
    for block in soup.select(".division, .row"):
        label_span = block.find("span", class_="semibold")
        if label_span and label_str in label_span.get_text():
            return get_text_clean(block, label_span.get_text(strip=True))

    # Stratégie B : Recherche texte libre
    target = soup.find(lambda tag: tag.name in ["p", "div", "li"] and label_str_colon in tag.get_text())
    
    if target:
        link = target.find('a')
        if link and label_str not in link.get_text(): 
            return link.get_text(strip=True)
        return get_text_clean(target, label_str_colon)

    return None

def extract_publications(soup):
    """ Récupère la liste des publications. """
    publications = []
    container = soup.select_one("#text-publs")
    if container:
        for p in container.find_all("p"):
            p_clean = copy.copy(p)
            icon = p_clean.find("i", class_="fa-thumb-tack")
            if icon: icon.decompose()
            text = p_clean.get_text(" ", strip=True)
            if text: publications.append(text)
    return publications

def extract_greek_text(soup):
    """ Récupère le texte grec formaté. """
    content_div = soup.find(id="words-full-text")
    if not content_div:
        return None
    
    temp_soup = copy.copy(content_div)
    for tooltip in temp_soup.find_all("span", class_="tooltiptext"):
        tooltip.decompose()
    for br in temp_soup.find_all("br"):
        br.replace_with("\n")
        
    text_content = temp_soup.get_text()
    lines = [line.strip() for line in text_content.split('\n')]
    return "\n".join(line for line in lines if line)

def extract_people(soup):
    """ Récupère la liste des personnes (onglet People). """
    names = []
    people_list = soup.find(id="people-list")
    if people_list:
        items = people_list.find_all("li", class_="item-large")
        for item in items:
            name_text = item.get_text(strip=True)
            if name_text: names.append(name_text)
    return names

def extract_places(soup):
    """ Récupère la liste des lieux (onglet Places). """
    places = []
    places_list = soup.find(id="places-list")
    if places_list:
        items = places_list.find_all("li", class_="item-large")
        for item in items:
            place_text = item.get_text(strip=True)
            if place_text: places.append(place_text)
    return places

def extract_irregularities(soup):
    """ Récupère la liste des irrégularités (onglet Text Irregularities). """
    irregularities = []
    # Cible l'ID 'texirr-list'
    irr_list = soup.find(id="texirr-list")
    if irr_list:
        items = irr_list.find_all("li", class_="item-large")
        for item in items:
            text = item.get_text(strip=True)
            if text: irregularities.append(text)
    return irregularities

# --- 3. LOGIQUE PRINCIPALE DE SCRAPING ---

def scrape_trismegistos_ultimate(start_index=1, end_index=10):
    base_url = "https://www.trismegistos.org/text/"
    results = {}

    print("--- Initialisation du navigateur Selenium ---")
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # -- Phase de sécurité (Captcha) --
        print(f"Chargement initial : {base_url}1")
        driver.get(f"{base_url}1")

        print("\n" + "="*60)
        print("PAUSE DE SÉCURITÉ (40s).")
        print("Veuillez résoudre le CAPTCHA si nécessaire.")
        print("="*60 + "\n")
        
        for i in range(40, 0, -1):
            sys.stdout.write(f"\rReprise dans {i} s...")
            sys.stdout.flush()
            time.sleep(1)
        print("\n\nLancement du scraping complet...\n")

        # -- Boucle sur les IDs --
        for i in range(start_index, end_index + 1):
            main_url = f"{base_url}{i}"
            people_url = f"{base_url}{i}#people"
            places_url = f"{base_url}{i}#places"
            irregularities_url = f"{base_url}{i}#text-irregularities"
            
            print(f"[{i}] Traitement complet...")

            # Initialisation du dictionnaire (sans Status)
            item_data = {
                "id": i,
                "url": main_url,
                "Language": None,
                "Content": None,
                "Date": None,
                "Provenance": None,
                "Material": None,
                "Publications": [],
                "GreekText": None,
                "People": [],
                "Places": [],
                "Irregularities": []
            }

            try:
                # ÉTAPE 1 : Page principale (Métadonnées + Texte)
                driver.get(main_url)
                time.sleep(random.uniform(1.0, 1.5))
                soup_main = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Vérification 404
                if "Page not found" in soup_main.text or "No record found" in soup_main.text:
                    print(f"  -> Page vide/inexistante.")
                else:
                    # Extraction métadonnées
                    item_data["Language"] = extract_field(soup_main, "Language/script")
                    item_data["Content"] = extract_field(soup_main, "Content (beta!)")
                    item_data["Date"] = extract_field(soup_main, "Date")
                    item_data["Provenance"] = extract_field(soup_main, "Provenance")
                    item_data["Material"] = extract_field(soup_main, "Material")
                    item_data["Publications"] = extract_publications(soup_main)
                    item_data["GreekText"] = extract_greek_text(soup_main)

                    # ÉTAPE 2 : People
                    driver.get(people_url)
                    time.sleep(1.5)
                    soup_people = BeautifulSoup(driver.page_source, 'html.parser')
                    item_data["People"] = extract_people(soup_people)
                    
                    # ÉTAPE 3 : Places
                    driver.get(places_url)
                    time.sleep(1.5)
                    soup_places = BeautifulSoup(driver.page_source, 'html.parser')
                    item_data["Places"] = extract_places(soup_places)
                    
                    # ÉTAPE 4 : Irregularities
                    driver.get(irregularities_url)
                    time.sleep(1.5)
                    soup_irr = BeautifulSoup(driver.page_source, 'html.parser')
                    item_data["Irregularities"] = extract_irregularities(soup_irr)

                    # Logs
                    p_count = len(item_data["People"])
                    pl_count = len(item_data["Places"])
                    irr_count = len(item_data["Irregularities"])
                    print(f"  -> Ppl: {p_count} | Places: {pl_count} | Irr: {irr_count}")

            except Exception as e:
                print(f"  -> Erreur sur ID {i}: {e}")

            results[str(i)] = item_data

    except Exception as global_e:
        print(f"Erreur critique du driver : {global_e}")
    finally:
        driver.quit()
        print("Navigateur fermé.")

    return results

if __name__ == "__main__":
    data = scrape_trismegistos_ultimate(start_index=1, end_index=10)
    
    filename = 'trismegistos_data_papyrus_1-10.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTerminé ! Base de données sauvegardée dans '{filename}'")