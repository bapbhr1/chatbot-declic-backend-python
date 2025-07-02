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

# Constantes fixes
COLLECTION_NAME = "wordpress_content"
EMBEDDING_MODEL = "text-embedding-3-large"
CHUNK_MAX_LENGTH = 500

def get_client_paths(client_id):
    base_path = Path("data/clients") / client_id
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

    return contents

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

    # Supprime l'ancien dossier chroma si existe
    if paths["chroma_dir"].exists():
        shutil.rmtree(paths["chroma_dir"])

    client = chromadb.PersistentClient(path=str(paths["chroma_dir"]))
    collection = client.create_collection(COLLECTION_NAME)

    contents = load_content(paths["content_file"], paths["manual_file"])
    all_chunks, metadatas, ids = [], [], []
    idx = 0

    for item in contents:
        chunks = chunk_text(item["content"], CHUNK_MAX_LENGTH)
        for chunk in chunks:
            all_chunks.append(chunk)
            metadatas.append({
                "title": item.get("title", ""),
                "url": item.get("url", "manuel"),
                "type": item.get("type", "manuel")
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

    print(f"Embeddings indexés dans {paths['chroma_dir']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python index_embeddings.py <client_id>")
        sys.exit(1)
    client_id = sys.argv[1]
    build_chroma_collection(client_id)
