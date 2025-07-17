# Chatbot Declic - Backend Python (Docker)

## Description
Ce backend centralise la gestion des données, l’indexation, l’API Flask et tous les scripts pour le chatbot WordPress. **Tout fonctionne dans un conteneur Docker sur le serveur distant.**

---

## Architecture
- **Serveur** : `51.254.126.20` (ou ton IP/nom de domaine)
- **Backend Python** : Docker (Flask + scripts)
- **Données** : montées en volume (`/root/chatbot-wp-declic/data/clients/`)
- **Scripts Python** : montés en volume (`/root/chatbot-wp-declic/scripts/`)
- **Plugin WordPress** : communique uniquement avec l’API Flask du backend

---

## Déploiement & Lancement

### 1. Construction de l’image Docker
Depuis `/root/chatbot-wp-declic/` :
```bash
docker build -t chatbot-backend .
```

### 2. Lancement du conteneur (avec scripts et données en volume)
```bash
docker run -d -p 5000:5000 \
  -v /root/chatbot-wp-declic/data/clients:/app/data/clients \
  -v /root/chatbot-wp-declic/scripts:/app/scripts \
  -v /root/chatbot-wp-declic/.env:/app/.env \
  -e CHATBOT_CLIENTS_PATH=/app/data/clients \
  --name chatbot-backend \
  chatbot-backend
```
- Le backend Flask écoute sur le port 5000.
- Les données **et le code Python** sont persistants et modifiables à chaud sur le serveur.

### 3. Accès à l’API Flask
- Depuis le serveur :
  ```bash
  curl http://localhost:5000/clients
  ```
- Depuis le plugin WordPress :
  - Utilise l’URL `http://<ip_serveur>:5000/` pour toutes les requêtes API.

### 4. Lancer un script Python dans le conteneur
```bash
docker exec -it chatbot-backend python scripts/recup_contenu_wp.py <client_id>
docker exec -it chatbot-backend python scripts/index_embeddings.py <client_id>
```

---

## Développement & Maintenance
- **Modifie les scripts Python directement sur le serveur** (`/root/chatbot-wp-declic/scripts/`) : les changements sont pris en compte instantanément dans le conteneur.
- **Pas besoin de rebuild l’image Docker** pour chaque modif de code Python.
- Si tu modifies les dépendances (`requirements.txt`), fais :
  ```bash
  docker exec -it chatbot-backend pip install -r requirements.txt
  ```
- Pour voir les logs Flask :
  ```bash
  docker logs -f chatbot-backend
  ```
- Pour accéder à un shell dans le conteneur :
  ```bash
  docker exec -it chatbot-backend bash
  ```

---

## Gestion des données
- Toutes les données clients sont dans `/root/chatbot-wp-declic/data/clients/` (sur le serveur, monté dans Docker).
- Les scripts Python et l’API Flask manipulent ces fichiers.
- **Ne jamais lancer les scripts en local** : tout doit se faire dans le conteneur Docker.

---

## Variables d’environnement
- `CHATBOT_CLIENTS_PATH` : chemin interne au conteneur pour les données clients (`/app/data/clients`)
- Clé OpenAI : à placer dans `.env` à la racine du projet ou du dossier `scripts/`.

---

## Résumé
- **Un seul centre de vérité** : toutes les données et scripts sont sur le serveur, accessibles via Docker.
- **Le plugin WordPress ne communique qu’avec l’API Flask**.
- **Administration, indexation, récupération, tout se fait dans le conteneur Docker**.
- **Développement facilité** : modifie les scripts Python à chaud sans rebuild.

---

*Pour toute modification, édite le code ou les données sur le serveur, et c’est pris en compte instantanément dans le conteneur.*