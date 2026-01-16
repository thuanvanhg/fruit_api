from neo4j import GraphDatabase
import os

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

def run_cypher(query, params=None):
    with driver.session(database="neo4j") as session:  # 👈 RẤT QUAN TRỌNG
        result = session.run(query, params or {})
        return [record.data() for record in result]


    
