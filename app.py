from flask import Flask, jsonify, request
from flask_cors import CORS
from mongo_client import fruit_col
from neo4j_client import run_cypher
import os

app = Flask(__name__)

CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/")
def home():
    return "Fruit API is running"

# ================= SEARCH =================
@app.route("/api/fruits/search", methods=["GET"])
def search_fruit():
    keyword = request.args.get("q", "").strip()
    if not keyword:
        return jsonify({"error": "Thiếu tham số q"}), 400

    mongo_results = list(
        fruit_col.find(
            {
                "$or": [
                    {"name_vi": {"$regex": keyword, "$options": "i"}},
                    {"name_en": {"$regex": keyword, "$options": "i"}}
                ]
            },
            {"_id": 0}
        )
    )

    results = []
    for fruit in mongo_results:
        cypher = """
        MATCH (f:Fruit {fruit_id:$fruit_id})
        OPTIONAL MATCH (f)-[:CO_CONG_DUNG]->(u:Use)
        RETURN collect(u.name) AS cong_dung
        """
        g = run_cypher(cypher, {"fruit_id": fruit["fruit_id"]})
        cong_dung = g[0]["cong_dung"] if g else []

        results.append({
            "fruit_id": fruit["fruit_id"],
            "name_vi": fruit.get("name_vi"),
            "name_en": fruit.get("name_en"),
            "cong_dung": cong_dung,
            "detail": fruit
        })

    return jsonify({
        "query": keyword,
        "total": len(results),
        "results": results
    })


# ================= DASHBOARD =================
@app.route("/api/stats/dashboard", methods=["GET"])
def stats_dashboard():
    try:
        total_fruits_mongo = fruit_col.count_documents({})

        fruits_by_season = list(fruit_col.aggregate([
            {"$unwind": "$harvest_season"},
            {"$group": {"_id": "$harvest_season", "count": {"$sum": 1}}},
        ]))

        fruits_by_region = list(fruit_col.aggregate([
            {"$unwind": "$regions"},
            {"$group": {"_id": "$regions", "count": {"$sum": 1}}},
        ]))

        cypher_overview = """
        MATCH (f:Fruit)
        OPTIONAL MATCH (f)-[:CO_CONG_DUNG]->(u:Use)
        RETURN count(DISTINCT f) AS total_fruits,
               count(DISTINCT u) AS total_cong_dung
        """
        overview = run_cypher(cypher_overview)[0]

        return jsonify({
            "mongo": {
                "total_fruits": total_fruits_mongo,
                "by_season": fruits_by_season,
                "by_region": fruits_by_region
            },
            "neo4j": overview
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
