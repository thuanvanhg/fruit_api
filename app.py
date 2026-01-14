from flask import Flask, jsonify, request
from mongo_client import fruit_col
from neo4j_client import run_cypher

app = Flask(__name__)

@app.route("/api/fruits/search", methods=["GET"])
def search_fruit():
    keyword = request.args.get("q", "").strip()

    if not keyword:
        return jsonify({"error": "Thiếu tham số q"}), 400

    # 1️⃣ SEARCH TRONG MONGODB (ĐÚNG SCHEMA)
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

    # 2️⃣ VỚI MỖI FRUIT → LẤY BENEFIT TỪ NEO4J
    for fruit in mongo_results:
        cypher = """
        MATCH (f:Fruit {fruit_id:$fruit_id})
        OPTIONAL MATCH (f)-[:HAS_BENEFIT]->(b:Benefit)
        RETURN collect(b.name) AS benefits
        """
        graph_data = run_cypher(cypher, {"fruit_id": fruit["fruit_id"]})

        benefits = graph_data[0]["benefits"] if graph_data else []

        results.append({
            "fruit_id": fruit.get("fruit_id"),
            "name_vi": fruit.get("name_vi"),
            "name_en": fruit.get("name_en"),
            "benefits": benefits,
            "detail": fruit
        })

    return jsonify({
        "query": keyword,
        "total": len(results),
        "results": results
    })

@app.route("/api/fruits", methods=["POST"])
def create_fruit():
    data = request.json
    if not data or "fruit_id" not in data:
        return jsonify({"error": "Thiếu fruit_id"}), 400

    # 1) MongoDB
    fruit_col.insert_one(data)

    # 2) Neo4j (node + benefit)
    cypher = """
    MERGE (f:Fruit {fruit_id:$fruit_id})
    WITH f
    UNWIND $benefits AS b
    MERGE (be:Benefit {name:b})
    MERGE (f)-[:HAS_BENEFIT]->(be)
    """
    run_cypher(cypher, {
        "fruit_id": data["fruit_id"],
        "benefits": data.get("benefits", [])
    })

    return jsonify({"msg": "Created"}), 201

@app.route("/api/fruits/<fruit_id>", methods=["GET"])
def get_fruit_by_id(fruit_id):
    mongo = fruit_col.find_one({"fruit_id": fruit_id}, {"_id": 0})
    if not mongo:
        return jsonify({"error": "Not found"}), 404

    cypher = """
    MATCH (f:Fruit {fruit_id:$fruit_id})
    OPTIONAL MATCH (f)-[:HAS_BENEFIT]->(b:Benefit)
    RETURN collect(b.name) AS benefits
    """
    g = run_cypher(cypher, {"fruit_id": fruit_id})
    benefits = g[0]["benefits"] if g else []

    return jsonify({
        "fruit_id": fruit_id,
        "detail": mongo,
        "benefits": benefits
    })

@app.route("/api/fruits/<fruit_id>", methods=["PUT"])
def update_fruit(fruit_id):
    data = request.json or {}

    # 1) MongoDB
    fruit_col.update_one(
        {"fruit_id": fruit_id},
        {"$set": {k:v for k,v in data.items() if k != "benefits"}}
    )

    # 2) Neo4j: sync benefits
    if "benefits" in data:
        cypher = """
        MATCH (f:Fruit {fruit_id:$fruit_id})-[r:HAS_BENEFIT]->()
        DELETE r
        WITH f
        UNWIND $benefits AS b
        MERGE (be:Benefit {name:b})
        MERGE (f)-[:HAS_BENEFIT]->(be)
        """
        run_cypher(cypher, {
            "fruit_id": fruit_id,
            "benefits": data.get("benefits", [])
        })

    return jsonify({"msg": "Updated"})

@app.route("/api/fruits/<fruit_id>", methods=["DELETE"])
def delete_fruit(fruit_id):
    # MongoDB
    fruit_col.delete_one({"fruit_id": fruit_id})

    # Neo4j
    cypher = "MATCH (f:Fruit {fruit_id:$fruit_id}) DETACH DELETE f"
    run_cypher(cypher, {"fruit_id": fruit_id})

    return jsonify({"msg": "Deleted"})

@app.route("/api/stats/dashboard", methods=["GET"])
def stats_dashboard():
    # ===== 1. MONGODB STATS =====
    total_fruits_mongo = fruit_col.count_documents({})

    fruits_by_season = list(fruit_col.aggregate([
        {"$unwind": "$harvest_season"},
        {"$group": {"_id": "$harvest_season", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))

    fruits_by_region = list(fruit_col.aggregate([
        {"$unwind": "$regions"},
        {"$group": {"_id": "$regions", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))

    # ===== 2. NEO4J STATS =====
    # Tổng số fruit + benefit
    cypher_overview = """
    MATCH (f:Fruit)
    OPTIONAL MATCH (f)-[:HAS_BENEFIT]->(b:Benefit)
    RETURN count(DISTINCT f) AS total_fruits,
           count(DISTINCT b) AS total_benefits
    """
    graph_overview = run_cypher(cypher_overview)[0]

    # Top fruit theo số benefit
    cypher_top = """
    MATCH (f:Fruit)-[:HAS_BENEFIT]->(b:Benefit)
    RETURN f.fruit_id AS fruit_id,
           count(b) AS benefit_count
    ORDER BY benefit_count DESC
    LIMIT 5
    """
    top_fruits = run_cypher(cypher_top)

    # ===== 3. RESPONSE DASHBOARD =====
    return jsonify({
        "mongo": {
            "total_fruits": total_fruits_mongo,
            "by_season": fruits_by_season,
            "by_region": fruits_by_region
        },
        "neo4j": {
            "total_fruits": graph_overview["total_fruits"],
            "total_benefits": graph_overview["total_benefits"],
            "top_fruits_by_benefits": top_fruits
        }
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
