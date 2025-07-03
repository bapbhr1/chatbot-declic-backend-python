import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path

def load_client_config(client_id):
    # Toujours basé sur le dossier du script, pas le dossier courant
    config_path = Path(__file__).resolve().parent.parent / "data/clients" / client_id / "config.json"
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

    excluded_titles = config.get("excluded_titles", [])
    excluded_slugs = config.get("excluded_slugs", [])
    min_content_length = config.get("min_content_length", 100)

    if title in excluded_titles or slug in excluded_slugs:
        return False

    cleaned_content = clean_html(item["content"]["rendered"])
    if len(cleaned_content) < min_content_length:
        return False

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
        url = f"{base_api_url}/{content_type}?per_page={per_page}"
        print(f"🔍 Récupération de : {url}")
        response = requests.get(url)
        response.raise_for_status()

        items = response.json()
        for item in items:
            if not is_valid_entry(item, content_type, config):
                continue

            cleaned = {
                "id": item.get("id"),
                "type": content_type[:-1],  # "pages" -> "page"
                "title": item["title"]["rendered"].strip(),
                "slug": item["slug"],
                "url": item["link"],
                "content": clean_html(item["content"]["rendered"])
            }
            all_data.append(cleaned)

    return all_data

def save_to_file(client_id, data):
    output_file = Path(__file__).resolve().parent.parent / "data/clients" / client_id / "content.json"
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nContenu sauvegardé dans {output_file} ({len(data)} éléments)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python recup_contenu_wp.py [client_id]")
        sys.exit(1)

    client_id = sys.argv[1]
    config = load_client_config(client_id)
    content = fetch_and_clean_content(config)
    save_to_file(client_id, content)
