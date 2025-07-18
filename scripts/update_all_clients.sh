#!/bin/bash

# Ajouter /usr/local/bin au PATH
export PATH="/usr/local/bin:$PATH"

# Définir la variable d'environnement pour les scripts Python
export CHATBOT_CLIENTS_PATH="/app/data/clients"

CLIENTS_DIR="/app/data/clients"
SCRIPTS_DIR="/app/scripts"
LOGS_DIR="/app/logs"

# Rotation des logs : un fichier par jour avec suppression auto après 30 jours
LOG_FILE="$LOGS_DIR/auto_update_$(date +%Y%m%d).log"

# Supprimer les logs de plus de 30 jours
find "$LOGS_DIR" -name "auto_update_*.log" -mtime +30 -delete 2>/dev/null || true

echo "=== Début mise à jour automatique $(date) ===" | tee -a "$LOG_FILE"

# Vérifier que le dossier clients existe
if [ ! -d "$CLIENTS_DIR" ]; then
    echo "Erreur: Le dossier clients n'existe pas: $CLIENTS_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

# Compteurs
total_clients=0
success_clients=0
error_clients=0

# Parcourir tous les clients
for client_dir in "$CLIENTS_DIR"/*/; do
    if [ -d "$client_dir" ]; then
        client_id=$(basename "$client_dir")
        total_clients=$((total_clients + 1))
        
        echo "Mise à jour du client: $client_id" | tee -a "$LOG_FILE"
        
        # Aller dans le bon répertoire
        cd /app
        
        # Récupération du contenu avec timeout 30 min
        echo "  → Récupération du contenu pour $client_id..." | tee -a "$LOG_FILE"
        if timeout 1800 /usr/local/bin/python3 "$SCRIPTS_DIR/recup_contenu_wp.py" "$client_id" >> "$LOG_FILE" 2>&1; then
            echo "  ✓ Contenu récupéré pour $client_id" | tee -a "$LOG_FILE"
            # Indexation avec timeout 30 min
            echo "  → Indexation pour $client_id..." | tee -a "$LOG_FILE"
            if timeout 1800 /usr/local/bin/python3 "$SCRIPTS_DIR/index_embeddings.py" "$client_id" >> "$LOG_FILE" 2>&1; then
                echo "  ✓ Indexation terminée pour $client_id" | tee -a "$LOG_FILE"
                success_clients=$((success_clients + 1))
            else
                echo "  ✗ Erreur indexation pour $client_id (timeout ou erreur)" | tee -a "$LOG_FILE"
                error_clients=$((error_clients + 1))
            fi
        else
            echo "  ✗ Erreur récupération contenu pour $client_id (timeout ou erreur)" | tee -a "$LOG_FILE"
            error_clients=$((error_clients + 1))
        fi
        
        echo "" | tee -a "$LOG_FILE"
    fi
done

# Résumé
echo "=== Résumé de la mise à jour $(date) ===" | tee -a "$LOG_FILE"
echo "Total des clients: $total_clients" | tee -a "$LOG_FILE"
echo "Succès: $success_clients" | tee -a "$LOG_FILE"
echo "Erreurs: $error_clients" | tee -a "$LOG_FILE"
echo "=== Fin mise à jour automatique ===" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Code de sortie : 0 si tout s'est bien passé, 1 s'il y a eu des erreurs
if [ $error_clients -eq 0 ]; then
    exit 0
else
    exit 1
fi
