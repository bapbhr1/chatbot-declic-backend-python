# Chatbot WordPress avec OpenAI et ChromaDB

## Description

Ce projet permet de créer un chatbot intelligent pour un site WordPress. Le chatbot répond aux questions des utilisateurs en s’appuyant sur le contenu du site (pages, articles, contenus manuels) indexé dans une base ChromaDB, et utilise l’API OpenAI GPT pour générer des réponses pertinentes et personnalisées.

## Fonctionnement général

1. **Extraction du contenu WordPress**  
   - Le script `scripts/recup_contenu_wp.py` récupère automatiquement les pages et articles du site WordPress via l’API REST, nettoie le contenu HTML, filtre les éléments non pertinents, puis sauvegarde le tout dans `content.json` pour chaque client.

2. **Ajout de contenu manuel**  
   - Le fichier `manual_content.json` permet d’ajouter des informations spécifiques ou complémentaires qui ne sont pas présentes sur le site WordPress.

3. **Indexation des embeddings**  
   - Le script `scripts/index_embeddings.py` découpe le contenu en morceaux, génère les embeddings OpenAI pour chaque passage, et les stocke dans une base ChromaDB locale propre à chaque client.

4. **Backend API**  
   - Le script `scripts/backend.py` lance un serveur Flask qui expose une API REST (`/ask`) pour interroger le chatbot depuis une interface web ou une application externe.

5. **Réponse du chatbot**  
   - Le script `scripts/chatbot_requete.py` gère la logique de recherche des passages les plus pertinents dans ChromaDB, construit le prompt pour GPT, et retourne la réponse générée.

## Structure des scripts

- `scripts/recup_contenu_wp.py` : Extraction et nettoyage du contenu WordPress.
- `scripts/index_embeddings.py` : Indexation des embeddings dans ChromaDB.
- `scripts/chatbot_requete.py` : Recherche contextuelle et génération de réponse via OpenAI.
- `scripts/backend.py` : API Flask pour exposer le chatbot en HTTP (POST `/ask`).

## Prérequis

- API REST activée sur le site WordPress
- Python 3.11.x (recommandé)
- Bibliothèques Python :  
  `openai`, `chromadb`, `python-dotenv`, `tqdm`, `flask`, `flask-cors`, `beautifulsoup4`, `requests`  
  (installer via `pip install -r requirements.txt`)

## Configuration

Chaque client possède son propre dossier dans `data/clients/<client_id>/` contenant :
- `config.json` : paramètres du client (site_url, prompt, etc.)
- `content.json` : contenu extrait du site WordPress
- `manual_content.json` : contenu manuel additionnel (optionnel)
- `chroma_db/` : base ChromaDB locale pour les embeddings

## Exemple de contenu pour manual_content.json

```
[
  {
    "id": "man-001",
    "type": "info",
    "title": "Coordonnées",
    "slug": "adresse",
    "content": "Notre agence est située au 2 avenue des Alliés, 57500 à Saint-Avold"
  },
  {
    "id": "man-002",
    "type": "info",
    "title": "Notre Facebook",
    "slug": "réseaux",
    "content": "Nous sommes présents sur les réseaux et voici d'ailleurs le lien vers notre page Facebook : https://www.facebook.com/Declic.Communication"
  }
]
```

## Utilisation

1. **Récupérer le contenu WordPress**  
   ```bash
   python scripts/recup_contenu_wp.py <client_id>
   ```

2. **Indexer les embeddings**  
   ```bash
   python scripts/index_embeddings.py <client_id>
   ```

3. **Lancer le backend Flask**  
   ```bash
   python scripts/backend.py
   ```
   L’API sera disponible sur http://localhost:5000/ask

4. **Interroger le chatbot**  
   Envoyer une requête POST à `/ask` avec un JSON :
   ```json
   {
     "question": "Votre question ici",
     "client_id": "<client_id>"
   }
   ```

## Personnalisation

Dans `config.json` ou dans le script `chatbot_requete.py`, vous pouvez ajuster :
- `system_prompt` : personnalité et rôle de l’IA
- `temperature` : créativité des réponses (0 = précis, 1 = créatif)
- `top_k_results` : nombre de passages contextuels fournis à GPT
- `max_tokens` : longueur maximale de la réponse