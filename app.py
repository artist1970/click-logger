from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

click_log = []

@app.route('/log', methods=['POST'])
def log_click():
    data = request.json
    click_log.append(data)
    print("New click:", data)  # for debugging/logging
    return jsonify({"status": "ok"})

@app.route('/stats', methods=['GET'])
def get_stats():
    return jsonify(click_log)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)