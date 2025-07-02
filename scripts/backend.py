from flask import Flask, request, jsonify
from chatbot_requete import chatbot_response
from flask_cors import CORS
from pathlib import Path

app = Flask(__name__)
CORS(app)  # Autorise les requêtes cross-origin

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question", "")
    client_id = data.get("client_id", "default")  # client_id par défaut si absent

    if not question:
        return jsonify({"error": "Pas de question fournie"}), 400

    try:
        answer = chatbot_response(question, client_id=client_id)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/clients", methods=["GET"])
def list_clients():
    clients_dir = Path("data/clients")
    clients = [d.name for d in clients_dir.iterdir() if d.is_dir()]
    return jsonify({"clients": clients})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
