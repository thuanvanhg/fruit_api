import os
import psycopg2

def get_pg_conn():
    return psycopg2.connect(
        os.environ["POSTGRES_URL"],
        sslmode="require"
    )

