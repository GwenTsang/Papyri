from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import time
import random
import sys
import copy

# --- FONCTIONS UTILITAIRES D'EXTRACTION (BS4) ---

def get_text_clean(soup_element, label_to_remove):
    """ Nettoie le texte (supprime tooltips et labels). """
    if not soup_element:
        return None
    temp_elem = copy.copy(soup_element)
    for tooltip in temp_elem.select(".tooltiptext"):
        tooltip.decompose()
    full_text = temp_elem.get_text(" ", strip=True)
    clean_text = full_text.replace(label_to_remove, "", 1).strip(" :\u00A0")
    return clean_text if clean_text else None

def extract_field(soup, label_str):
    """ Récupère une métadonnée simple (Date, Langue, etc.). """
    label_str_colon = label_str + ":"
    
    # Stratégie 1 : Bloc .division
    for block in soup.select(".division, .row"):
        label_span = block.find("span", class_="semibold")
        if label_span and label_str in label_span.get_text():
            return get_text_clean(block, label_span.get_text(strip=True))

    # Stratégie 2 : Texte libre
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
            if p_clean.find("i", class_="fa-thumb-tack"):
                p_clean.find("i", class_="fa-thumb-tack").decompose()
            text = p_clean.get_text(" ", strip=True)
            if text:
                publications.append(text)
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
    lines = [line.strip() for line in temp_soup.get_text().split('\n')]
    return "\n".join(line for line in lines if line)

def extract_people_list(soup):
    """
    Récupère la liste des personnes dans l'onglet #people.
    Cible: <ul id="people-list"> -> <li class="item-large">
    """
    names = []
    people_list = soup.find(id="people-list")
    
    if people_list:
        # On cherche les éléments <li> avec la classe 'item-large'
        items = people_list.find_all("li", class_="item-large")
        for item in items:
            name_text = item.get_text(strip=True)
            if name_text:
                names.append(name_text)
    
    return names

# --- PROCESSUS PRINCIPAL ---

def scrape_trismegistos_ultimate(start_index=1, end_index=10):
    base_url = "https://www.trismegistos.org/text/"
    results = {}

    print("--- Initialisation Selenium ---")
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless") 
    
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # 1. Gestion Captcha
        print(f"Connexion initiale : {base_url}1")
        driver.get(f"{base_url}1")

        print("\n" + "="*60)
        print("PAUSE DE SÉCURITÉ (40s) - Validez le Captcha SVP.")
        print("="*60 + "\n")
        
        for i in range(40, 0, -1):
            sys.stdout.write(f"\rReprise dans {i} s...")
            sys.stdout.flush()
            time.sleep(1)
        print("\n\nLancement du scraping...\n")

        # 2. Boucle sur les IDs
        for i in range(start_index, end_index + 1):
            
            # --- ÉTAPE A : MÉTADONNÉES & TEXTE GREC ---
            url_main = f"{base_url}{i}"
            print(f"ID {i} : Traitement principal...")
            
            item_data = {
                "id": i,
                "url": url_main,
                "Language": None,
                "Content": None,
                "Date": None,
                "Provenance": None,
                "Material": None,
                "Publications": [],
                "GreekText": None,
                "People": [], # Nouveau champ
                "Status": "OK"
            }

            try:
                # Navigation page principale
                driver.get(url_main)
                time.sleep(random.uniform(1.0, 1.5))
                
                soup_main = BeautifulSoup(driver.page_source, 'html.parser')
                
                if "Page not found" in soup_main.text or "No record found" in soup_main.text:
                    print(f"  -> Page vide/inexistante.")
                    item_data["Status"] = "Not Found"
                else:
                    # Extraction infos principales
                    item_data["Language"] = extract_field(soup_main, "Language/script")
                    item_data["Content"] = extract_field(soup_main, "Content (beta!)")
                    item_data["Date"] = extract_field(soup_main, "Date")
                    item_data["Provenance"] = extract_field(soup_main, "Provenance")
                    item_data["Material"] = extract_field(soup_main, "Material")
                    item_data["Publications"] = extract_publications(soup_main)
                    item_data["GreekText"] = extract_greek_text(soup_main)
                    
                    # --- ÉTAPE B : NOMS DES PERSONNES ---
                    # On navigue vers l'onglet People pour forcer le chargement ou l'affichage
                    url_people = f"{base_url}{i}#people"
                    # print(f"  -> Récupération des personnes...")
                    driver.get(url_people)
                    
                    # Petite pause pour laisser le temps au JS/Hash de réagir
                    time.sleep(1.5)
                    
                    # Parsing de la page (qui est maintenant sur l'onglet People)
                    soup_people = BeautifulSoup(driver.page_source, 'html.parser')
                    people_list = extract_people_list(soup_people)
                    item_data["People"] = people_list
                    
                    # Logs de confirmation
                    lang = item_data["Language"] or "?"
                    nb_ppl = len(people_list)
                    print(f"  -> OK | Lang: {lang} | Mat: {item_data['Material']} | Personnes: {nb_ppl}")

            except Exception as e:
                print(f"  -> Erreur sur ID {i}: {e}")
                item_data["Status"] = "Error"
                item_data["Error"] = str(e)

            results[str(i)] = item_data

    except Exception as global_e:
        print(f"Erreur critique : {global_e}")
    finally:
        driver.quit()

    return results

if __name__ == "__main__":
    # Exécution sur les 10 premières pages
    data = scrape_trismegistos_ultimate(start_index=1, end_index=10)
    
    filename = 'trismegistos_complete_with_people.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nDonnées complètes sauvegardées dans '{filename}'")