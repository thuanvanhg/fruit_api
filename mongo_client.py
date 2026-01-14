import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["fruit_graph"]                 # database

fruit_col = db["fnodes_fruit_clear"] 
