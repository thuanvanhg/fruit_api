from flask import Flask, jsonify, request
from flask_cors import CORS
from mongo_client import fruit_col
from neo4j_client import run_cypher

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/")
def home():
    return "Fruit API is running"


# ================= TEST NEO4J =================
@app.route("/api/neo4j/test")
def test_neo4j():
    try:
        r = run_cypher("RETURN 1 AS ok")
        return jsonify(r)
    except Exception as e:
        return jsonify({"neo4j_error": str(e)}), 500


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
        try:
            cypher = """
            MATCH (f:Fruit {fruit_id:$fruit_id})
            OPTIONAL MATCH (f)-[:CO_CONG_DUNG|HAS_BENEFIT|HAS_USE]->(u)
            RETURN collect(DISTINCT u.name) AS cong_dung
            """
            g = run_cypher(cypher, {"fruit_id": fruit["fruit_id"]})
            cong_dung = g[0]["cong_dung"] if g else []
        except Exception as e:
            cong_dung = []
            print("Neo4j error (search):", e)

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
    # ---------- Mongo ----------
    total_fruits_mongo = fruit_col.count_documents({})

    fruits_by_season = list(fruit_col.aggregate([
        {"$unwind": "$harvest_season"},
        {"$group": {"_id": "$harvest_season", "count": {"$sum": 1}}}
    ]))

    fruits_by_region = list(fruit_col.aggregate([
        {"$unwind": "$regions"},
        {"$group": {"_id": "$regions", "count": {"$sum": 1}}}
    ]))

    # ---------- Neo4j ----------
    try:
        cypher = """
        MATCH (f:Fruit)
        OPTIONAL MATCH (f)-[:CO_CONG_DUNG|HAS_BENEFIT|HAS_USE]->(u)
        RETURN count(DISTINCT f) AS total_fruits,
               count(DISTINCT u) AS total_cong_dung
        """
        r = run_cypher(cypher)
        neo4j_stats = r[0] if r else {
            "total_fruits": 0,
            "total_cong_dung": 0
        }
    except Exception as e:
        print("Neo4j error (dashboard):", e)
        neo4j_stats = {
            "error": str(e),
            "total_fruits": 0,
            "total_cong_dung": 0
        }

    return jsonify({
        "mongo": {
            "total_fruits": total_fruits_mongo,
            "by_season": fruits_by_season,
            "by_region": fruits_by_region
        },
        "neo4j": neo4j_stats
    })
