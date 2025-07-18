import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import re

# Chemin des clients, défini par la variable d'environnement CHATBOT_CLIENTS_PATH
CLIENTS_PATH = Path(os.environ.get("CHATBOT_CLIENTS_PATH", "/root/chatbot-wp-declic/data/clients/"))

def load_client_config(client_id):
    config_path = CLIENTS_PATH / client_id / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Config client introuvable : {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def is_valid_entry(item, content_type, config):
    title = item["title"]["rendered"].strip().lower()
    slug = item["slug"].lower()
    status = item.get("status", "publish").lower()

    excluded_titles = config.get("excluded_titles", [])
    excluded_slugs = config.get("excluded_slugs", [])
    min_content_length = config.get("min_content_length", 100)

    # Exclure si le statut n'est pas 'publish'
    if status != "publish":
        return False

    # Exclure si le titre ou le slug est explicitement dans la config
    if title in excluded_titles or slug in excluded_slugs:
        return False

    cleaned_content = clean_html(item["content"]["rendered"])
    if len(cleaned_content) < min_content_length:
        return False

    # Ajouter ici d'autres critères d'exclusion si besoin (catégories, métadonnées, etc.)

    return True

def fetch_and_clean_content(config):
    site_url = config.get("site_url")
    if not site_url:
        raise ValueError("L'URL du site WordPress (site_url) n'est pas définie dans la config client")

    content_types = config.get("content_types", ["pages", "posts"])
    per_page = config.get("per_page", 100)

    all_data = []

    # Construire la base de l'API WP (ex: https://monsite.com/wp-json/wp/v2)
    base_api_url = site_url.rstrip("/") + "/wp-json/wp/v2"

    for content_type in content_types:
        page = 1
        while True:
            url = f"{base_api_url}/{content_type}?per_page={per_page}&page={page}"
            print(f"🔍 Récupération de : {url}")
            response = requests.get(url)
            if response.status_code == 400 and 'rest_post_invalid_page_number' in response.text:
                # Fin de la pagination
                break
            response.raise_for_status()
            items = response.json()
            if not items:
                break
            for item in items:
                if not is_valid_entry(item, content_type, config):
                    continue
                cleaned = {
                    "id": item.get("id"),
                    "type": content_type[:-1],  # "pages" -> "page"
                    "title": item["title"]["rendered"].strip(),
                    "slug": item["slug"],
                    "url": item["link"],
                    "content": clean_html(item["content"]["rendered"]),
                    "modified": item.get("modified")  # Ajout de la date de modification
                }
                all_data.append(cleaned)
            if len(items) < per_page:
                break
            page += 1
    return all_data

def save_to_file(client_id, data):
    output_file = CLIENTS_PATH / client_id / "content.json"
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nContenu sauvegardé dans {output_file} ({len(data)} éléments)")

def normalize_content(text):
    # Supprime les espaces, retours à la ligne, met en minuscule et enlève tout ce qui n'est pas lettre ou chiffre
    if not isinstance(text, str):
        return ''
    # Décodage des entités HTML éventuelles
    try:
        from html import unescape
        text = unescape(text)
    except ImportError:
        pass
    # Supprime tout ce qui n'est pas lettre ou chiffre (y compris ponctuation, balises résiduelles, etc.)
    text = re.sub(r'[^\w\d]', '', text.lower())
    return text

def compare_modification_dates(old_path, new_path):
    def load_json(path):
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    old = {item.get("url", item.get("content", "")): item for item in load_json(old_path)}
    new = {item.get("url", item.get("content", "")): item for item in load_json(new_path)}
    changed = []
    for k, v in new.items():
        if k in old:
            old_date = old[k].get("modified")
            new_date = v.get("modified")
            if old_date != new_date:
                changed.append({"title": v.get("title"), "url": v.get("url"), "old_date": old_date, "new_date": new_date})
    if changed:
        print("\nChangements détectés :")
        for c in changed:
            print(f"- {c['title']} ({c['url']}) : {c['old_date']} -> {c['new_date']}")
    else:
        print("\nAucun changement détecté sur le site web. Pas de mise à jour nécessaire.")

def summarize_differences_by_date(old_path, new_path, should_index_path=None):
    def load_json(path):
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    old = {item.get("url", item.get("content", "")): item for item in load_json(old_path)}
    new = {item.get("url", item.get("content", "")): item for item in load_json(new_path)}
    added = [v for k, v in new.items() if k not in old]
    removed = [v for k, v in old.items() if k not in new]
    modified = [v for k, v in new.items() if k in old and v.get("modified") != old[k].get("modified")]
    # On vérifie si le fichier should_index.txt existait déjà avant
    should_index_already_present = should_index_path and os.path.exists(should_index_path)
    if not added and not removed and not modified:
        print("\nAucun changement détecté."
        "\nContenu manuel mis à jour si modifié et enregistré.")
        # Ne supprime le fichier should_index.txt que s'il n'existait pas déjà (créé par le plugin)
        if should_index_path and os.path.exists(should_index_path) and not should_index_already_present:
            os.remove(should_index_path)
        return False
    print("\nRésumé des différences :")
    print(f"  Ajoutés : {len(added)}")
    print(f"  Supprimés : {len(removed)}")
    print(f"  Modifiés : {len(modified)}")
    if added:
        print("\nNouveaux contenus :")
        for v in added:
            print("-", v.get("title", v.get("url", "?")))
    if removed:
        print("\nContenus supprimés :")
        for v in removed:
            print("-", v.get("title", v.get("url", "?")))
    if modified:
        print("\nContenus modifiés :")
        for v in modified:
            print("-", v.get("title", v.get("url", "?")))
    print ("\nMise à jour des nouvelles données en cours")   
    print("\nContenu manuel mis à jour si modifié et enregistré.")
    # Crée le fichier should_index
    if should_index_path:
        with open(should_index_path, "w") as f:
            f.write("index")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python recup_contenu_wp.py [client_id]")
        sys.exit(1)
    client_id = sys.argv[1]
    config = load_client_config(client_id)
    output_file = CLIENTS_PATH / client_id / "content.json"
    old_file = str(output_file) + ".old"
    should_index_file = CLIENTS_PATH / client_id / "should_index.txt"
    # Sauvegarde l'ancien contenu si existe
    if output_file.exists():
        os.rename(output_file, old_file)
    content = fetch_and_clean_content(config)
    save_to_file(client_id, content)
    # Compare l'ancien et le nouveau contenu
    if os.path.exists(old_file):
        summarize_differences_by_date(old_file, output_file, should_index_path=should_index_file)
        os.remove(old_file)
    else:
        # Premier run : toujours indexer
        with open(should_index_file, "w") as f:
            f.write("index")
