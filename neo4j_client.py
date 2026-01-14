import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(
        os.getenv("NEO4J_USER"),
        os.getenv("NEO4J_PASSWORD")
    )
)

def run_cypher(query, params=None):
    with driver.session() as session:
        result = session.run(query, params or {})
        return [r.data() for r in result]


    