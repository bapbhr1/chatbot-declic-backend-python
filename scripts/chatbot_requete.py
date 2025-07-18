import os
import json
from dotenv import load_dotenv
import openai
import chromadb
from pathlib import Path

# Chargement de la clé API OpenAI
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuration par défaut
AI_CONFIG = {
    "openai_model": "gpt-4o-mini",
    "embedding_model": "text-embedding-3-large",
    "system_prompt": "Tu es un assistant IA du site. Renseigne les visiteurs de manière claire et utile.",
    "top_k_results": 5,
    "temperature": 0.4,
    "max_tokens": 300,
    "collection_name": "wordpress_content"
}

# Chemin des clients, défini par la variable d'environnement CHATBOT_CLIENTS_PATH
CLIENTS_PATH = Path(os.environ.get("CHATBOT_CLIENTS_PATH", "/root/chatbot-wp-declic/data/clients/"))

def load_client_config(client_id):
    config_path = CLIENTS_PATH / client_id / "config.json"
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_embedding(text, model):
    response = openai.embeddings.create(input=text, model=model)
    return response.data[0].embedding

def search_chroma(query, chroma_dir, collection_name, embedding_model, top_k):
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)
    query_embedding = get_embedding(query, embedding_model)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k ,  
        include=["documents", "metadatas"]
    )
    # Associer chaque chunk à sa metadata
    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []
    # Fusionner et trier par date de modification (décroissante)
    passages = []
    for doc, meta in zip(docs, metas):
        passages.append({
            "content": doc,
            "modified": meta.get("modified", "1970-01-01"),
            "title": meta.get("title", ""),
            "url": meta.get("url", "")
        })
    
    return passages[:top_k]

def build_prompt(user_query, contexts, system_prompt):
    prompt = "Voici des extraits du site :\n"
    for i, context in enumerate(contexts):
        date_str = f" (modifié le {context['modified']})" if context.get('modified') else ""
        prompt += f"[Passage {i+1}{date_str}]: {context['content']}\n"
    prompt += f"\nQuestion : {user_query}\n"
    prompt += (
        "Réponds de manière professionnelle, amicale et concise. "
        "Si tu n'as pas la réponse à la question, n'invente rien."
    )
    return prompt

def ask_gpt(prompt, system_prompt, model, temperature, max_tokens):
    response = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

def chatbot_response(user_question, client_id="default"):
    client_conf = load_client_config(client_id)

    # Paramètres avec fallback sur config globale
    system_prompt = client_conf.get("system_prompt", AI_CONFIG["system_prompt"])
    top_k = client_conf.get("top_k_results", AI_CONFIG["top_k_results"])
    temperature = client_conf.get("temperature", AI_CONFIG["temperature"])
    max_tokens = client_conf.get("max_tokens", AI_CONFIG["max_tokens"])
    openai_model = client_conf.get("openai_model", AI_CONFIG["openai_model"])
    embedding_model = client_conf.get("embedding_model", AI_CONFIG["embedding_model"])
    chroma_dir = client_conf.get("chroma_dir", str(CLIENTS_PATH / client_id / "chroma_db"))
    collection_name = client_conf.get("collection_name", AI_CONFIG["collection_name"])

    contexts = search_chroma(user_question, chroma_dir, collection_name, embedding_model, top_k)
    prompt = build_prompt(user_question, contexts, system_prompt)
    return ask_gpt(prompt, system_prompt, openai_model, temperature, max_tokens)



