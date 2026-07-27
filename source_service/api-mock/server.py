from flask import Flask, jsonify

app = Flask(__name__)

# Datos de ejemplo
DOCUMENTS = [
    {"id": "1", "metadata": {"name": "doc1.pdf", "size": 1024}},
    {"id": "2", "metadata": {"name": "doc2.pdf", "size": 2048}},
    {"id": "3", "metadata": {"name": "doc3.pdf", "size": 512}},
]


@app.route('/documents', methods=['GET'])
def list_documents():
    return jsonify(DOCUMENTS)


@app.route('/documents/<doc_id>', methods=['GET'])
def get_document(doc_id):
    doc = next((d for d in DOCUMENTS if d['id'] == doc_id), None)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    # Simular contenido binario (texto plano)
    return jsonify({
        "id": doc['id'],
        "metadata": doc['metadata'],
        "content": f"Contenido del documento {doc_id}"
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
