from flask import Flask, jsonify, request
from flask_cors import CORS
from mongo_client import fruit_col
from neo4j_client import run_cypher

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ================= ROOT =================
@app.route("/")
def home():
    return "Fruit API is running"


# ================= DEBUG ROUTES =================
@app.route("/api/routes")
def list_routes():
    return jsonify(sorted([str(r) for r in app.url_map.iter_rules()]))

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
        cong_dung = []
        try:
            cypher = """
            MATCH (f:Fruit {fruit_id:$fruit_id})
            OPTIONAL MATCH (f)-[:CO_CONG_DUNG|HAS_BENEFIT|HAS_USE]->(u)
            RETURN collect(DISTINCT u.name) AS cong_dung
            """
            r = run_cypher(cypher, {"fruit_id": fruit.get("fruit_id")})
            if r and r[0].get("cong_dung"):
                cong_dung = r[0]["cong_dung"]
        except Exception as e:
            print("Neo4j error (search):", e)

        results.append({
            "fruit_id": fruit.get("fruit_id"),
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
        {"$unwind": {"path": "$harvest_season", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": "$harvest_season", "count": {"$sum": 1}}}
    ]))

    fruits_by_region = list(fruit_col.aggregate([
        {"$unwind": {"path": "$regions", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": "$regions", "count": {"$sum": 1}}}
    ]))

    # ---------- Neo4j ----------
    neo4j_stats = {
        "total_fruits": 0,
        "total_cong_dung": 0
    }

    try:
        cypher = """
        MATCH (f:Fruit)
        OPTIONAL MATCH (f)-[:CO_CONG_DUNG|HAS_BENEFIT|HAS_USE]->(u)
        RETURN count(DISTINCT f) AS total_fruits,
               count(DISTINCT u) AS total_cong_dung
        """
        r = run_cypher(cypher)
        if r:
            neo4j_stats = r[0]
    except Exception as e:
        print("Neo4j error (dashboard):", e)
        neo4j_stats["error"] = str(e)

    return jsonify({
        "mongo": {
            "total_fruits": total_fruits_mongo,
            "by_season": fruits_by_season,
            "by_region": fruits_by_region
        },
        "neo4j": neo4j_stats
    })
@app.route("/api/version")
def api_version():
    return "VERSION_2026_01_16"

