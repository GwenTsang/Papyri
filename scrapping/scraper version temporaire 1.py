from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import time
import random
import sys
import copy

# --- FONCTIONS UTILITAIRES D'EXTRACTION ---

def get_text_clean(soup_element, label_to_remove):
    """
    Nettoie le texte d'un champ simple (Date, Provenance, Material).
    """
    if not soup_element:
        return None
    
    # On travaille sur une copie pour ne pas modifier l'objet soup original
    temp_elem = copy.copy(soup_element)
    
    # Suppression des tooltips (infobulles cachées)
    for tooltip in temp_elem.select(".tooltiptext"):
        tooltip.decompose()
    
    full_text = temp_elem.get_text(" ", strip=True)
    # On retire le label et les séparateurs
    clean_text = full_text.replace(label_to_remove, "", 1).strip(" :\u00A0")
    
    return clean_text if clean_text else None

def extract_field(soup, label_str):
    """
    Cherche une métadonnée simple (Date, Provenance, Material).
    """
    label_str_colon = label_str + ":"
    
    # Stratégie 1 : Recherche via bloc .division (souvent Date/Provenance)
    for block in soup.select(".division, .row"):
        label_span = block.find("span", class_="semibold")
        if label_span and label_str in label_span.get_text():
            return get_text_clean(block, label_span.get_text(strip=True))

    # Stratégie 2 : Recherche texte générique (souvent Material)
    target = soup.find(lambda tag: tag.name in ["p", "div", "li"] and label_str_colon in tag.get_text())
    
    if target:
        link = target.find('a')
        # Si le lien ne contient pas le label lui-même, c'est la valeur
        if link and label_str not in link.get_text(): 
            return link.get_text(strip=True)
        return get_text_clean(target, label_str_colon)

    return None

def extract_publications(soup):
    """
    Extrait la liste des publications situées dans le bloc #text-publs.
    """
    publications = []
    container = soup.select_one("#text-publs")
    
    if container:
        paragraphs = container.find_all("p")
        for p in paragraphs:
            p_clean = copy.copy(p)
            
            # On enlève l'icône "thumb-tack"
            icon = p_clean.find("i", class_="fa-thumb-tack")
            if icon:
                icon.decompose()
                
            text = p_clean.get_text(" ", strip=True)
            if text:
                publications.append(text)
                
    return publications

def extract_greek_text(soup):
    """
    Extrait le texte grec ancien en suivant la logique robuste :
    - Cible la div id="words-full-text"
    - Supprime les tooltips (.tooltiptext)
    - Remplace les <br> par des sauts de ligne \n
    - Nettoie les espaces
    """
    content_div = soup.find(id="words-full-text")
    
    if not content_div:
        return None
    
    # On travaille sur une copie pour isoler le traitement
    temp_soup = copy.copy(content_div)

    # 1. Supprimer les tooltips (métadonnées grammaticales)
    for tooltip in temp_soup.find_all("span", class_="tooltiptext"):
        tooltip.decompose()

    # 2. Remplacer les <br> par des sauts de ligne pour garder la structure
    for br in temp_soup.find_all("br"):
        br.replace_with("\n")

    # 3. Extraire le texte
    text_content = temp_soup.get_text()

    # 4. Nettoyage ligne par ligne
    lines = [line.strip() for line in text_content.split('\n')]
    clean_text = "\n".join(line for line in lines if line)

    return clean_text

# --- FONCTION PRINCIPALE DE SCRAPING ---

def scrape_trismegistos_complete(start_index=1, end_index=10):
    base_url = "https://www.trismegistos.org/text/"
    results = {}

    print("--- Initialisation du navigateur Selenium ---")
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless") # Décommenter pour cacher le navigateur
    
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # 1. Accès initial pour contourner la sécurité (Cloudflare/Captcha)
        print(f"Chargement initial : {base_url}1")
        driver.get(f"{base_url}1")

        print("\n" + "="*60)
        print("PAUSE DE SÉCURITÉ (40s).")
        print("Résolvez le CAPTCHA ou la vérification 'Human' maintenant.")
        print("="*60 + "\n")
        
        for i in range(40, 0, -1):
            sys.stdout.write(f"\rReprise dans {i} s...")
            sys.stdout.flush()
            time.sleep(1)
        print("\n\nLancement du scraping complet...\n")

        # 2. Boucle sur les IDs
        for i in range(start_index, end_index + 1):
            url = f"{base_url}{i}"
            print(f"Traitement ID {i} : {url}")
            
            item_data = {
                "id": i,
                "url": url,
                "Date": None,
                "Provenance": None,
                "Material": None,
                "Publications": [],
                "GreekText": None,  # Nouveau champ
                "Status": "OK"
            }

            try:
                driver.get(url)
                # Pause "humaine"
                time.sleep(random.uniform(1.0, 2.0))
                
                # Parsing via BeautifulSoup
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                if "Page not found" in soup.text or "No record found" in soup.text:
                    print(f"  -> Page vide ou inexistante.")
                    item_data["Status"] = "Not Found"
                else:
                    # Extraction Métadonnées
                    item_data["Date"] = extract_field(soup, "Date")
                    item_data["Provenance"] = extract_field(soup, "Provenance")
                    item_data["Material"] = extract_field(soup, "Material")
                    
                    # Extraction Publications
                    item_data["Publications"] = extract_publications(soup)
                    
                    # Extraction Texte Grec
                    greek = extract_greek_text(soup)
                    item_data["GreekText"] = greek
                    
                    # Feedback console
                    has_greek = "OUI" if greek else "NON"
                    nb_pubs = len(item_data["Publications"])
                    print(f"  -> Données récupérées | Texte Grec: {has_greek} | Pubs: {nb_pubs}")

            except Exception as e:
                print(f"  -> Erreur sur ID {i}: {e}")
                item_data["Status"] = "Error"
                item_data["Error"] = str(e)

            results[str(i)] = item_data

    except Exception as global_e:
        print(f"Erreur critique du driver : {global_e}")
    finally:
        print("Fermeture du navigateur.")
        driver.quit()

    return results

if __name__ == "__main__":
    # Paramètres : scrap des pages 1 à 10
    data = scrape_trismegistos_complete(start_index=1, end_index=10)
    
    # Sauvegarde JSON
    filename = 'trismegistos_full_data.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\nTerminé ! Données sauvegardées dans '{filename}'")
