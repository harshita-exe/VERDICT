"""
Flask web app for the AI Code Review Agent.
Serves a single page where anyone can paste code and get a live review.
"""

from flask import Flask, render_template, request, jsonify
from agent import review_code, review_project

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/review", methods=["POST"])
def api_review():
    data = request.get_json()
    code = data.get("code", "").strip()

    if not code:
        return jsonify({"error": "Please paste some code to review."}), 400

    try:
        result = review_code(code)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500


@app.route("/api/review-project", methods=["POST"])
def api_review_project():
    data = request.get_json()
    files = data.get("files", [])

    if not files:
        return jsonify({"error": "Please upload at least one file."}), 400

    try:
        result = review_project(files)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
