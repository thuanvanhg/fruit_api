from flask import Flask, jsonify, request
from flask_cors import CORS   # 👈 THÊM
from dotenv import load_dotenv
load_dotenv()
from mongo_client import fruit_col
from neo4j_client import run_cypher
from postgres_client import get_pg_conn

app = Flask(__name__)
CORS(app)   # 👈 THÊM DÒNG NÀY
@app.route("/")
def home():
    return "API is running."
# ================= SEARCH =================
import re
from unidecode import unidecode

@app.route("/api/fruits/search", methods=["GET"])
def search_fruit():
    keyword = request.args.get("q", "").strip().lower()

    if not keyword:
        return jsonify({"error": "Thiếu tham số q"}), 400

    # bỏ dấu keyword
    keyword_nodau = unidecode(keyword)
    safe_keyword = re.escape(keyword_nodau)

    mongo_results = list(
        fruit_col.find(
            {
                "$or": [
                    {"name_vi_nodau": {"$regex": safe_keyword, "$options": "i"}},
                    {"name_en": {"$regex": safe_keyword, "$options": "i"}}
                ]
            },
            {"_id": 0}
        )
    )

    results = []
    for fruit in mongo_results:
        results.append({
            "fruit_id": fruit.get("fruit_id"),
            "name_vi": fruit.get("name_vi"),
            "name_en": fruit.get("name_en"),
            "detail": fruit
        })

    return jsonify({
        "query": keyword,
        "total": len(results),
        "results": results
    })

# ================= CREATE =================
@app.route("/api/fruits", methods=["POST"])
def create_fruit():
    data = request.json
    if not data or "fruit_id" not in data:
        return jsonify({"error": "Thiếu fruit_id"}), 400

    # MongoDB
    fruit_col.insert_one(data)

    # Neo4j
    cypher = """
    MERGE (f:Fruit {fruit_id:$fruit_id})
    WITH f
    UNWIND $cong_dung AS cd
    MERGE (u:Use {name:cd})
    MERGE (f)-[:CO_CONG_DUNG]->(u)
    """
    run_cypher(cypher, {
        "fruit_id": data["fruit_id"],
        "cong_dung": data.get("benefits", [])
    })

    return jsonify({"msg": "Created"}), 201


# ================= GET BY ID =================
@app.route("/api/fruits/<fruit_id>", methods=["GET"])
def get_fruit_by_id(fruit_id):
    mongo = fruit_col.find_one({"fruit_id": fruit_id}, {"_id": 0})
    if not mongo:
        return jsonify({"error": "Not found"}), 404

    cypher = """
    MATCH (f {fruit_id:$fruit_id})
    OPTIONAL MATCH (f)-[:CO_CONG_DUNG]->(u)
    RETURN collect(u.name) AS cong_dung
    """
    g = run_cypher(cypher, {"fruit_id": fruit_id})
    cong_dung = g[0]["cong_dung"] if g else []

    return jsonify({
        "fruit_id": fruit_id,
        "detail": mongo,
        "cong_dung": cong_dung
    })


# ================= UPDATE =================
@app.route("/api/fruits/<fruit_id>", methods=["PUT"])
def update_fruit(fruit_id):
    data = request.json or {}

    # MongoDB
    fruit_col.update_one(
        {"fruit_id": fruit_id},
        {"$set": {k: v for k, v in data.items() if k != "benefits"}}
    )

    # Neo4j sync công dụng
    if "benefits" in data:
        cypher = """
        MATCH (f {fruit_id:$fruit_id})-[r:CO_CONG_DUNG]->()
        DELETE r
        WITH f
        UNWIND $cong_dung AS cd
        MERGE (u:Use {name:cd})
        MERGE (f)-[:CO_CONG_DUNG]->(u)
        """
        run_cypher(cypher, {
            "fruit_id": fruit_id,
            "cong_dung": data.get("benefits", [])
        })

    return jsonify({"msg": "Updated"})


# ================= DELETE =================
@app.route("/api/fruits/<fruit_id>", methods=["DELETE"])
def delete_fruit(fruit_id):
    fruit_col.delete_one({"fruit_id": fruit_id})
    run_cypher(
        "MATCH (f {fruit_id:$fruit_id}) DETACH DELETE f",
        {"fruit_id": fruit_id}
    )
    return jsonify({"msg": "Deleted"})


# ================= DASHBOARD =================
@app.route("/api/stats/dashboard", methods=["GET"])
def stats_dashboard():
    try:
        # ===== MONGODB =====
        total_fruits_mongo = fruit_col.count_documents({})

        fruits_by_season = list(fruit_col.aggregate([
            {"$match": {"harvest_season": {"$exists": True, "$ne": []}}},
            {"$unwind": "$harvest_season"},
            {"$group": {"_id": "$harvest_season", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]))

        fruits_by_region = list(fruit_col.aggregate([
            {"$match": {"regions": {"$exists": True, "$ne": []}}},
            {"$unwind": "$regions"},
            {"$group": {"_id": "$regions", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]))

        # ===== NEO4J =====
        cypher_overview = """
        MATCH (f)
        OPTIONAL MATCH (f)-[:CO_CONG_DUNG]->(u)
        RETURN count(DISTINCT f) AS total_fruits,
               count(DISTINCT u) AS total_cong_dung
        """
        graph_overview = run_cypher(cypher_overview)[0]

        cypher_top = """
        MATCH (f)-[:CO_CONG_DUNG]->(u)
        RETURN f.fruit_id AS fruit_id,
               count(u) AS cong_dung_count
        ORDER BY cong_dung_count DESC
        LIMIT 5
        """
        top_fruits = run_cypher(cypher_top)

        return jsonify({
            "mongo": {
                "total_fruits": total_fruits_mongo,
                "by_season": fruits_by_season,
                "by_region": fruits_by_region
            },
            "neo4j": {
                "total_fruits": graph_overview["total_fruits"],
                "total_cong_dung": graph_overview["total_cong_dung"],
                "top_fruits_by_cong_dung": top_fruits
            }
        })

    except Exception as e:
        return jsonify({
            "error": "Dashboard failed",
            "detail": str(e)
        }), 500


# ================= POSTGRES =================

@app.route("/api/postgres/test")
def postgres_test():
    conn = get_pg_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM fruit;")
    count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "db": "postgresql",
        "table": "fruit",
        "count": count
    }
    
@app.route("/api/postgres/fruits")
def postgres_fruits():
    conn = get_pg_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT fruit_id, name_vi
        FROM fruit
        ORDER BY fruit_id
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "fruit_id": r[0],
            "name_vi": r[1]
        } for r in rows
    ])
   

import os

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )

