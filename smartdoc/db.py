"""PostgreSQL connection factory; callers own transaction boundaries."""
import psycopg
from psycopg.rows import dict_row
from .config import database_url

def connect():
    return psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=5)
