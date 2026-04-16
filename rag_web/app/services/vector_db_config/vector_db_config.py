import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

user = os.getenv("VECTOR_DB_USER")
password = quote_plus(os.getenv("VECTOR_DB_PASSWORD"))  # encode special chars
host = os.getenv("VECTOR_DB_HOST")
port = os.getenv("VECTOR_DB_PORT")
db = os.getenv("VECTOR_DB_NAME")

VECTOR_DB_CONNECTION_STRING = (
    f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
)

