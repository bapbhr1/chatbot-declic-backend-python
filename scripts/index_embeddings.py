import os
import sys
import json
import shutil
import openai
import chromadb
from tqdm import tqdm
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

openai.api_key = os.getenv("OPENAI_API_KEY")

# === IMPORTANT ===
# Ce script doit être exécuté sur le serveur, jamais en local.
# Le chemin des clients est défini par la variable d'environnement CHATBOT_CLIENTS_PATH
# ou par défaut '/root/chatbot-wp-declic/data/clients/'
CLIENTS_PATH = Path(os.environ.get("CHATBOT_CLIENTS_PATH", "/root/chatbot-wp-declic/data/clients/"))

# Constantes fixes
COLLECTION_NAME = "wordpress_content"
EMBEDDING_MODEL = "text-embedding-3-large"
CHUNK_MAX_LENGTH = 500

def get_client_paths(client_id):
    base_path = CLIENTS_PATH / client_id
    return {
        "content_file": base_path / "content.json",
        "manual_file": base_path / "manual_content.json",
        "chroma_dir": base_path / "chroma_db",
    }

def load_content(content_file, manual_file):
    contents = []

    if content_file.exists():
        with open(content_file, "r", encoding="utf-8") as f:
            contents += json.load(f)
    else:
        print(f"Fichier introuvable : {content_file}")

    if manual_file.exists():
        with open(manual_file, "r", encoding="utf-8") as f:
            contents += json.load(f)
    else:
        print(f"Aucun contenu manuel trouvé dans {manual_file} (facultatif).")

    if not contents:
        raise FileNotFoundError("Aucun contenu à indexer trouvé.")

    # --- FILTRAGE EFFICACE ---
    def is_valid(item):
        
        # Exclure certains types
        if item.get("type") in {"draft", "private"}:
            return False
        # Exclure certaines urls/pages
        url = item.get("url", "")
        if any(excl in url for excl in ["mentions-legales", "cgu", "politique-confidentialite"]):
            return False
        return True

    # Supprimer les doublons par URL
    seen_urls = set()
    filtered = []
    for item in contents:
        url = item.get("url")
        if url and url in seen_urls:
            continue
        if is_valid(item):
            filtered.append(item)
            if url:
                seen_urls.add(url)
    if not filtered:
        raise FileNotFoundError("Aucun contenu à indexer après filtrage.")
    return filtered

def chunk_text(text, max_length):
    paragraphs = text.split("\n")
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) < max_length:
            current += p + "\n"
        else:
            chunks.append(current.strip())
            current = p + "\n"
    if current:
        chunks.append(current.strip())
    return chunks

def get_embedding(text):
    response = openai.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

def build_chroma_collection(client_id):
    paths = get_client_paths(client_id)
    chroma_dir = paths["chroma_dir"]
    chroma_dir_tmp = chroma_dir.parent / "chroma_db_new"
    should_index_file = chroma_dir.parent / "should_index.txt"

    # Vérification du fichier témoin should_index.txt
    if not should_index_file.exists():
        print("Aucun changement détecté, indexation ignorée.")
        return

    # Nettoyage du dossier temporaire s'il existe déjà
    if chroma_dir_tmp.exists():
        shutil.rmtree(chroma_dir_tmp)

    # Création de la nouvelle base dans le dossier temporaire
    if hasattr(chromadb, "PersistentClient"):
        client = chromadb.PersistentClient(path=str(chroma_dir_tmp))
    else:
        client = chromadb.Client()  # Pas de persistance si pas de PersistentClient
    collection = client.create_collection(COLLECTION_NAME)

    contents = load_content(paths["content_file"], paths["manual_file"])
    all_chunks, metadatas, ids = [], [], []
    idx = 0

    for item in contents:
        chunks = chunk_text(item["content"], CHUNK_MAX_LENGTH)
        for chunk in chunks:
            all_chunks.append(chunk)
            metadatas.append({
                "title": item.get("title", "manuel"),
                "url": item.get("url", "manuel"),
                "type": item.get("type", "manuel"),
                "modified": item.get("modified", "")  # Ajout de la date de modification
            })
            ids.append(str(idx))
            idx += 1

    print(f"Génération des embeddings pour {len(all_chunks)} chunks...")

    embeddings = []
    for chunk in tqdm(all_chunks):
        emb = get_embedding(chunk)
        embeddings.append(emb)

    collection.add(
        documents=all_chunks,
        metadatas=metadatas,
        ids=ids,
        embeddings=embeddings
    )

    # Swap atomique : on ne remplace l'ancienne base que si la nouvelle est prête
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
    chroma_dir_tmp.rename(chroma_dir)
    print(f"Embeddings indexés dans {chroma_dir}")

    # Suppression du fichier should_index.txt après indexation
    if should_index_file.exists():
        os.remove(should_index_file)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python index_embeddings.py <client_id>")
        sys.exit(1)
    client_id = sys.argv[1]
    build_chroma_collection(client_id)
