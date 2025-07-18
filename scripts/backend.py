from flask import Flask, request, jsonify
from chatbot_requete import chatbot_response
from flask_cors import CORS
from pathlib import Path
import os
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import re

# Chemin des clients, défini par la variable d'environnement CHATBOT_CLIENTS_PATH
CLIENTS_PATH = Path(os.environ.get("CHATBOT_CLIENTS_PATH", "/root/chatbot-wp-declic/data/clients/"))

app = Flask(__name__)
CORS(app)  # Autorise les requêtes cross-origin

API_KEY = os.environ.get("CHATBOT_API_KEY", "chatbot-declic-default-key-2025")

def require_api_key(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key or key != API_KEY:
            return jsonify({"error": "Clé API invalide ou manquante"}), 401
        return f(*args, **kwargs)
    return decorated

def log_question(client_id, question, answer, user_ip=None):
    """Enregistre une question posée par un utilisateur avec structure organisée"""
    client_dir = CLIENTS_PATH / client_id
    if not client_dir.exists():
        return
    
    # Créer la structure: clients/client_id/questions_logs/2025/07/2025-07.json
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    month_filename = f"{year}-{month}.json"
    
    logs_dir = client_dir / "questions_logs" / year / month
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = logs_dir / month_filename
    
    # Charger les logs existants du mois
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []
    
    # Ajouter la nouvelle entrée
    log_entry = {
        "timestamp": now.isoformat(),
        "question": question,
        "answer": answer[:500] + "..." if len(answer) > 500 else answer,  # Tronquer la réponse
        "user_ip": user_ip,
        "client_id": client_id
    }
    
    logs.append(log_entry)
    
    # Sauvegarder en format lisible avec indentation
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur lors de l'enregistrement du log pour {client_id}: {e}")

def cleanup_old_logs(client_id, months_to_keep=12):
    """Supprime les logs de plus de X mois pour économiser l'espace"""
    client_dir = CLIENTS_PATH / client_id
    logs_base_dir = client_dir / "questions_logs"
    
    if not logs_base_dir.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=365)  # 1 an
    
    # Parcourir tous les dossiers d'années
    for year_dir in logs_base_dir.iterdir():
        if not year_dir.is_dir():
            continue
            
        # Parcourir tous les dossiers de mois
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
                
            try:
                # Construire la date du mois
                year_str = year_dir.name
                month_str = month_dir.name
                month_date = datetime.strptime(f"{year_str}-{month_str}", "%Y-%m")
                
                # Supprimer si trop ancien
                if month_date < cutoff_date:
                    import shutil
                    shutil.rmtree(month_dir)
                    print(f"🗑️  Supprimé logs anciens: {client_id}/{year_str}/{month_str}")
                    
            except ValueError:
                continue
    
    # Nettoyer les dossiers d'années vides
    for year_dir in logs_base_dir.iterdir():
        if year_dir.is_dir() and not any(year_dir.iterdir()):
            year_dir.rmdir()
            print(f"🗑️  Supprimé dossier année vide: {client_id}/{year_dir.name}")

@app.route("/ask", methods=["POST"])
@require_api_key
def ask():
    data = request.get_json()
    question = data.get("question", "")
    client_id = data.get("client_id", "default")  # client_id par défaut si absent

    if not question:
        return jsonify({"error": "Pas de question fournie"}), 400

    try:
        answer = chatbot_response(question, client_id=client_id)
        
        # Logger la question et la réponse
        user_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        log_question(client_id, question, answer, user_ip)
        
        # Nettoyage automatique des anciens logs (tous les 100 appels environ)
        import random
        if random.randint(1, 100) == 1:
            cleanup_old_logs(client_id)
        
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients", methods=["GET"])
@require_api_key
def list_clients():
    clients_dir = CLIENTS_PATH
    clients = [d.name for d in clients_dir.iterdir() if d.is_dir()]
    return jsonify({"clients": clients})

@app.route("/clients/<client_id>", methods=["GET"])
@require_api_key
def get_client_config(client_id):
    config_path = CLIENTS_PATH / client_id / "config.json"
    if not config_path.exists():
        return jsonify({"error": "Client ou config introuvable"}), 404
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>/manual_content", methods=["GET"])
@require_api_key
def get_manual_content(client_id):
    manual_path = CLIENTS_PATH / client_id / "manual_content.json"
    if not manual_path.exists():
        return jsonify([])  # Retourne une liste vide si pas de contenu
    try:
        with open(manual_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients", methods=["POST"])
@require_api_key
def create_client():
    data = request.get_json()
    client_id = data.get("client_id")
    if not client_id:
        return jsonify({"error": "client_id manquant"}), 400
    client_dir = CLIENTS_PATH / client_id
    if client_dir.exists():
        return jsonify({"error": "Client existe déjà"}), 400
    try:
        client_dir.mkdir(parents=True, exist_ok=True)
        config_path = client_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>", methods=["PUT"])
@require_api_key
def update_client_config(client_id):
    config_path = CLIENTS_PATH / client_id / "config.json"
    if not config_path.exists():
        return jsonify({"error": "Client introuvable"}), 404
    data = request.get_json()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>", methods=["DELETE"])
@require_api_key
def delete_client(client_id):
    import shutil
    client_dir = CLIENTS_PATH / client_id
    if not client_dir.exists():
        return jsonify({"error": "Client introuvable"}), 404
    try:
        shutil.rmtree(client_dir)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>/manual_content", methods=["PUT"])
@require_api_key
def update_manual_content(client_id):
    manual_path = CLIENTS_PATH / client_id / "manual_content.json"
    data = request.get_json()
    try:
        with open(manual_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Création du fichier should_index.txt à chaque modification du contenu manuel
        should_index_path = CLIENTS_PATH / client_id / "should_index.txt"
        with open(should_index_path, "w") as f:
            f.write("index")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>/update_data", methods=["POST"])
@require_api_key
def update_data(client_id):
    import subprocess
    try:
        # 1. Récupération du contenu (synchrone)
        result = subprocess.run(
            ["python", "scripts/recup_contenu_wp.py", client_id],
            capture_output=True, text=True, check=True
        )
        # 2. Indexation des embeddings (asynchrone, tâche de fond)
        subprocess.Popen([
            "python", "scripts/index_embeddings.py", client_id
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({
            "success": True,
            "output": result.stdout,
            "message": "Mise à jour du contenu terminée. L'indexation des embeddings est lancée en tâche de fond."
        })
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.stderr}), 500

@app.route("/clients/<client_id>/questions_log", methods=["GET"])
@require_api_key
def get_questions_log(client_id):
    """Récupère les logs des questions avec possibilité de choisir année/mois"""
    client_dir = CLIENTS_PATH / client_id
    
    # Paramètres optionnels pour spécifier l'année et le mois
    year = request.args.get('year', datetime.now().strftime("%Y"))
    month = request.args.get('month', datetime.now().strftime("%m"))
    
    log_file = client_dir / "questions_logs" / year / month / f"{year}-{month}.json"
    
    if not log_file.exists():
        return jsonify({
            "questions": [], 
            "total": 0, 
            "year": year, 
            "month": month,
            
            "file_path": str(log_file.relative_to(client_dir))
        })
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
        
        # Pagination
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Inverser l'ordre pour avoir les plus récentes en premier
        
        paginated_logs = logs[offset:offset+limit]
        
        return jsonify({
            "questions": paginated_logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset,
            "year": year,
            "month": month,
            "file_path": str(log_file.relative_to(client_dir))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients/<client_id>/questions_log/periods", methods=["GET"])
@require_api_key
def get_available_periods(client_id):
    """Liste toutes les périodes (années/mois) disponibles pour les logs"""
    client_dir = CLIENTS_PATH / client_id
    logs_base_dir = client_dir / "questions_logs"
    
    if not logs_base_dir.exists():
        return jsonify({"periods": []})
    
    periods = []
    
    # Parcourir la structure année/mois
    for year_dir in sorted(logs_base_dir.iterdir(), reverse=True):
        if not year_dir.is_dir():
            continue
            
        year = year_dir.name
        
        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue
                
            month = month_dir.name
            log_file = month_dir / f"{year}-{month}.json"
            
            if log_file.exists():
                # Compter le nombre de questions dans ce fichier
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                        question_count = len(logs)
                except:
                    question_count = 0
                
                periods.append(f"{year}-{month}")
    
    return jsonify({"periods": periods})

# Endpoint compatible avec le plugin WordPress (sans client_id dans l'URL)
@app.route("/questions_log/periods", methods=["GET"])
@require_api_key
def get_available_periods_wp():
    """Version compatible WordPress - périodes disponibles via paramètre client_id"""
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({"error": "client_id manquant"}), 400
    return get_available_periods(client_id)

@app.route("/clients/<client_id>/questions_stats", methods=["GET"])
@require_api_key
def get_questions_stats(client_id):
    """Récupère les statistiques des questions pour un client"""
    client_dir = CLIENTS_PATH / client_id
    logs_base_dir = client_dir / "questions_logs"
    
    if not logs_base_dir.exists():
        return jsonify({
            "total_questions": 0,
            "questions_today": 0,
            "questions_this_month": 0,
            "first_question_date": None,
            "last_question_date": None,
            "questions_by_month": {}
        })
    
    all_logs = []
    questions_by_month = {}
    
    # Parcourir tous les fichiers de logs pour ce client
    for year_dir in logs_base_dir.iterdir():
        if not year_dir.is_dir():
            continue
            
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
                
            year = year_dir.name
            month = month_dir.name
            log_file = month_dir / f"{year}-{month}.json"
            
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        month_logs = json.load(f)
                        all_logs.extend(month_logs)
                        questions_by_month[f"{year}-{month}"] = len(month_logs)
                except:
                    continue
    
    total_questions = len(all_logs)
    
    if total_questions == 0:
        return jsonify({
            "total_questions": 0,
            "questions_today": 0,
            "questions_this_month": 0,
            "first_question_date": None,
            "last_question_date": None,
            "questions_by_month": {}
        })
    
    # Calculer les statistiques
    now = datetime.now()
    today = now.date()
    current_month = now.strftime("%Y-%m")
    
    questions_today = 0
    questions_this_month = questions_by_month.get(current_month, 0)
    
    timestamps = []
    
    for log in all_logs:
        try:
            log_datetime = datetime.fromisoformat(log["timestamp"])
            timestamps.append(log_datetime)
            
            if log_datetime.date() == today:
                questions_today += 1
                
        except:
            continue
    
    # Dates de première et dernière question
    if timestamps:
        timestamps.sort()
        first_question_date = timestamps[0].isoformat()
        last_question_date = timestamps[-1].isoformat()
    else:
        first_question_date = None
        last_question_date = None
    
    return jsonify({
        "total_questions": total_questions,
        "questions_today": questions_today,
        "questions_this_month": questions_this_month,
        "first_question_date": first_question_date,
        "last_question_date": last_question_date,
        "questions_by_month": questions_by_month
    })

# Endpoint compatible avec le plugin WordPress (sans client_id dans l'URL)
@app.route("/questions_stats", methods=["GET"])
@require_api_key
def get_questions_stats_wp():
    """Version compatible WordPress - statistiques via paramètre client_id"""
    client_id = request.args.get('client_id')
    if not client_id:
        return jsonify({"error": "client_id manquant"}), 400
    return get_questions_stats(client_id)

# Endpoint compatible avec le plugin WordPress (sans client_id dans l'URL)
@app.route("/questions_log", methods=["GET"])
@require_api_key
def get_questions_log_wp():
    """Version compatible WordPress - logs via paramètres client_id et period"""
    client_id = request.args.get('client_id')
    period = request.args.get('period')
    
    if not client_id:
        return jsonify({"error": "client_id manquant"}), 400
    
    if not period:
        return jsonify({"error": "period manquant"}), 400
    
    # Séparer année et mois depuis le format "2025-07"
    try:
        year, month = period.split('-')
    except ValueError:
        return jsonify({"error": "Format de période invalide, attendu: YYYY-MM"}), 400
    
    client_dir = CLIENTS_PATH / client_id
    log_file = client_dir / "questions_logs" / year / month / f"{year}-{month}.json"
    
    if not log_file.exists():
        return jsonify({
            "questions": [], 
            "total": 0, 
            "period": period
        })
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
        
        # Pagination
        limit = request.args.get('limit', 1000, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Inverser l'ordre pour avoir les plus récentes en premier
        
        paginated_logs = logs[offset:offset+limit]
        
        return jsonify({
            "questions": paginated_logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset,
            "period": period
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/questions_frequent", methods=["GET"])
@require_api_key
def questions_frequent():
    """
    Endpoint pour obtenir les mots-clés fréquents et les questions similaires pour un client (et une période optionnelle)
    GET /questions_frequent?client_id=...&period=AAAA-MM
    """
    client_id = request.args.get('client_id')
    period = request.args.get('period')  # format AAAA-MM
    if not client_id:
        return jsonify({"error": "client_id manquant"}), 400

    client_dir = CLIENTS_PATH / client_id
    logs_base_dir = client_dir / "questions_logs"
    questions = []

    # Récupérer les logs selon la période
    if period:
        try:
            year, month = period.split('-')
        except ValueError:
            return jsonify({"error": "Format de période invalide, attendu: YYYY-MM"}), 400
        log_file = logs_base_dir / year / month / f"{year}-{month}.json"
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
                questions = [log["question"] for log in logs if "question" in log]
    else:
        # Toutes périodes
        for year_dir in logs_base_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                log_file = month_dir / f"{year_dir.name}-{month_dir.name}.json"
                if log_file.exists():
                    with open(log_file, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                        questions.extend([log["question"] for log in logs if "question" in log])

    # Extraction des mots-clés (stopwords FR/EN, mots > 3 lettres)
    stopwords = set([
        'le','la','les','un','une','des','du','de','d','en','et','ou','a','au','aux','pour','par','sur','avec','sans','dans','ce','cette','ces','mon','ma','mes','ton','ta','tes','son','sa','ses','notre','nos','votre','vos','leur','leurs','je','tu','il','elle','on','nous','vous','ils','elles','y','est','suis','es','sont','êtes','été','être','ai','as','avons','avez','ont','avoir','fait','fais','faisons','faites','font','faire','plus','moins','très','peu','beaucoup','comment','quoi','quel','quelle','quels','quelles','qui','que','qu','où','quand','donc','si','là','ça','c','se','sa','aujourd','hui','the','and','or','but','for','not','are','is','was','were','be','been','being','have','has','had','do','does','did','of','to','in','on','at','by','with','from','as','an','it','this','that','these','those','i','you','he','she','we','they','my','your','his','her','its','our','their','me','him','them','us','can','will','just','so','if','then','than','too','very','all','any','some','no','nor','also','because','about','into','over','after','before','such','why','how','which','what','who','whom','where','when','again','once','here','there','each','own','same','other','more','most','own','same','other','more','most','s','t','d','ll','m','o','re','ve','y','ain','aren','couldn','didn','doesn','hadn','hasn','haven','isn','ma','mightn','mustn','needn','shan','shouldn','wasn','weren','won','wouldn'
    ])
    word_counter = Counter()
    for q in questions:
        # Nettoyage basique
        q_clean = re.sub(r"[^\w\s]", " ", q.lower())
        words = [w for w in q_clean.split() if len(w) > 3 and w not in stopwords]
        word_counter.update(words)
    keywords = [
        {"word": word, "count": count}
        for word, count in word_counter.most_common(15)
    ]

    # Regroupement des questions similaires (fuzzy matching simple)
    from difflib import SequenceMatcher
    min_similarity = 0.7
    question_groups = []
    used = set()
    for i, q1 in enumerate(questions):
        if i in used:
            continue
        group = [q1]
        similar = []
        for j, q2 in enumerate(questions):
            if i != j and j not in used:
                ratio = SequenceMatcher(None, q1.lower(), q2.lower()).ratio()
                if ratio > min_similarity:
                    similar.append(q2)
                    used.add(j)
        used.add(i)
        question_groups.append({
            "question": q1,
            "count": 1 + len(similar),
            "similar": similar
        })
    # Trier par nombre d'occurrences
    question_groups = sorted(question_groups, key=lambda x: x["count"], reverse=True)[:10]

    return jsonify({
        "keywords": keywords,
        "frequent_questions": question_groups
    })

@app.route("/clients/<client_id>/update_logs", methods=["GET"])
@require_api_key
def get_update_logs(client_id):
    """
    Récupère les logs de mise à jour automatique pour un client spécifique
    Paramètres optionnels:
    - date: YYYY-MM-DD (par défaut: aujourd'hui)
    - lines: nombre de lignes à retourner (par défaut: 100)
    - search: rechercher un texte spécifique dans les logs
    """
    try:
        # Paramètres de la requête
        date_param = request.args.get("date", datetime.now().strftime("%Y%m%d"))
        lines_limit = int(request.args.get("lines", 100))
        search_term = request.args.get("search", "").strip().lower()
        
        # Construire le chemin du fichier de log
        logs_dir = Path("/app/logs")
        log_file = logs_dir / f"auto_update_{date_param}.log"
        
        if not log_file.exists():
            return jsonify({
                "client_id": client_id,
                "date": date_param,
                "logs": [],
                "message": f"Aucun log trouvé pour la date {date_param}"
            })
        
        # Lire le fichier de log
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Filtrer les logs pour ce client spécifique - RÉCUPÉRER TOUT
        client_logs = []
        in_client_section = False
        client_pattern = f"Mise à jour du client: {client_id}"
        next_client_pattern = "Mise à jour du client:"
        
        for i, line in enumerate(all_lines):
            original_line = line  # Garder la ligne originale avec ses espaces/indentations
            line_stripped = line.strip()
            
            # Début de la section pour notre client
            if client_pattern in line_stripped:
                in_client_section = True
                client_logs.append(original_line.rstrip())
                continue
            
            # Fin de la section - plus précis pour capturer TOUT jusqu'au prochain client
            if in_client_section:
                # Arrêter si on trouve un autre client OU le résumé final
                if (next_client_pattern in line_stripped and client_pattern not in line_stripped) or \
                   line_stripped.startswith("=== Résumé de la mise à jour"):
                    in_client_section = False
                    break
                
                # Sinon, ajouter TOUTE ligne qui fait partie de notre section
                client_logs.append(original_line.rstrip())
        
        # Si on est encore dans la section client à la fin du fichier, c'était le dernier client
        # On continue à ajouter les lignes jusqu'à la fin ou jusqu'au résumé
        if in_client_section:
            for j in range(i + 1, len(all_lines)):
                line_stripped = all_lines[j].strip()
                if line_stripped.startswith("=== Résumé de la mise à jour"):
                    break
                client_logs.append(all_lines[j].rstrip())
        
        # Appliquer le filtre de recherche si spécifié
        if search_term:
            client_logs = [line for line in client_logs if search_term in line.lower()]
        
        # Limiter le nombre de lignes
        if lines_limit > 0:
            client_logs = client_logs[-lines_limit:]
        
        # Informations supplémentaires - ANALYSE COMPLÈTE
        success_indicators = ["✓", "succès", "terminée"]
        error_indicators = ["✗", "erreur", "timeout", "échec"]
        
        has_success = any(any(indicator in line.lower() for indicator in success_indicators) for line in client_logs)
        has_errors = any(any(indicator in line.lower() for indicator in error_indicators) for line in client_logs)
        
        # Extraire TOUTES les informations détaillées
        extracted_info = {
            "urls_fetched": [],
            "content_summary": {},
            "differences": {},
            "modified_contents": [],
            "embedding_progress": [],
            "total_chunks": None,
            "final_progress": None,
            "execution_time": None,
            "database_path": None
        }
        
        for line in client_logs:
            line_clean = line.strip()
            
            # URLs récupérées
            if "🔍 Récupération de :" in line_clean:
                url_match = re.search(r"🔍 Récupération de : (.+)", line_clean)
                if url_match:
                    extracted_info["urls_fetched"].append(url_match.group(1))
            
            # Résumé du contenu sauvegardé
            elif "Contenu sauvegardé dans" in line_clean and "éléments" in line_clean:
                elements_match = re.search(r"\((\d+) éléments\)", line_clean)
                path_match = re.search(r"Contenu sauvegardé dans (.+?) \(", line_clean)
                if elements_match:
                    extracted_info["content_summary"]["total_elements"] = int(elements_match.group(1))
                if path_match:
                    extracted_info["content_summary"]["file_path"] = path_match.group(1)
            
            # Résumé des différences
            elif "Ajoutés :" in line_clean:
                added_match = re.search(r"Ajoutés : (\d+)", line_clean)
                if added_match:
                    extracted_info["differences"]["added"] = int(added_match.group(1))
            elif "Supprimés :" in line_clean:
                removed_match = re.search(r"Supprimés : (\d+)", line_clean)
                if removed_match:
                    extracted_info["differences"]["removed"] = int(removed_match.group(1))
            elif "Modifiés :" in line_clean:
                modified_match = re.search(r"Modifiés : (\d+)", line_clean)
                if modified_match:
                    extracted_info["differences"]["modified"] = int(modified_match.group(1))
            
            # Contenus modifiés spécifiques
            elif line_clean.startswith("- ") and any(keyword in line_clean.lower() for keyword in ["page", "article", "contenu", "offre"]):
                content_name = line_clean[2:].strip()  # Enlever "- "
                extracted_info["modified_contents"].append(content_name)
            
            # Génération des embeddings
            elif "Génération des embeddings pour" in line_clean:
                chunks_match = re.search(r"Génération des embeddings pour (\d+) chunks", line_clean)
                if chunks_match:
                    extracted_info["total_chunks"] = int(chunks_match.group(1))
            
            # Progression des embeddings (lignes avec %)
            elif "%" in line_clean and "|" in line_clean and "[" in line_clean:
                progress_match = re.search(r"(\d+)%", line_clean)
                if progress_match:
                    progress_percent = int(progress_match.group(1))
                    # Ne garder que certaines étapes pour éviter trop de données
                    if progress_percent % 10 == 0 or progress_percent in [1, 5, 95, 99, 100]:
                        extracted_info["embedding_progress"].append({
                            "percent": progress_percent,
                            "line": line_clean
                        })
                    extracted_info["final_progress"] = progress_percent
            
            # Chemin de la base de données
            elif "Embeddings indexés dans" in line_clean:
                db_match = re.search(r"Embeddings indexés dans (.+)", line_clean)
                if db_match:
                    extracted_info["database_path"] = db_match.group(1)
        
        # Calculer le temps d'exécution approximatif si on a des barres de progression
        if extracted_info["embedding_progress"]:
            # Prendre la dernière progression pour estimer le temps
            last_progress = extracted_info["embedding_progress"][-1]
            if last_progress["percent"] == 100:
                # Extraire le temps de la barre de progression finale
                time_match = re.search(r"\[(\d+:\d+)<", last_progress["line"])
                if time_match:
                    extracted_info["execution_time"] = time_match.group(1)
        
        return jsonify({
            "client_id": client_id,
            "date": date_param,
            "total_lines": len(client_logs),
            "has_success": has_success,
            "has_errors": has_errors,
            "extracted_info": extracted_info,
            "logs": client_logs,
            "search_term": search_term if search_term else None,
            "summary": {
                "urls_count": len(extracted_info["urls_fetched"]),
                "has_content_changes": bool(extracted_info["differences"]),
                "embedding_completed": extracted_info["final_progress"] == 100 if extracted_info["final_progress"] else False,
                "total_chunks_processed": extracted_info["total_chunks"],
                "execution_time": extracted_info["execution_time"]
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la lecture des logs: {str(e)}"}), 500

@app.route("/clients/<client_id>/update_logs/dates", methods=["GET"])
@require_api_key
def get_available_log_dates(client_id):
    """
    Récupère la liste des dates disponibles pour les logs de mise à jour
    """
    try:
        logs_dir = Path("/app/logs")
        log_files = list(logs_dir.glob("auto_update_*.log"))
        
        dates = []
        for log_file in log_files:
            # Extraire la date du nom de fichier (auto_update_YYYYMMDD.log)
            date_match = re.search(r"auto_update_(\d{8})\.log", log_file.name)
            if date_match:
                date_str = date_match.group(1)
                # Vérifier si ce client apparaît dans ce log
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        if f"Mise à jour du client: {client_id}" in content:
                            dates.append({
                                "date": date_str,
                                "formatted_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                                "file_size": log_file.stat().st_size
                            })
                except Exception:
                    continue
        
        # Trier par date décroissante (plus récent en premier)
        dates.sort(key=lambda x: x["date"], reverse=True)
        
        return jsonify({
            "client_id": client_id,
            "available_dates": dates,
            "total_files": len(dates)
        })
        
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la recherche des dates: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)


