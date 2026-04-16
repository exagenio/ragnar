import psycopg2
from psycopg2.extras import RealDictCursor


def sample_table_rows(db_connection, table_name, limit=10):
    """Sample table rows"""

    # Connect to database and fetch sample rows
    conn = psycopg2.connect(
        host=db_connection.host,
        port=db_connection.port,
        dbname=db_connection.database_name,
        user=db_connection.username,
        password=db_connection.password,
    )

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = f'SELECT * FROM "{table_name}" LIMIT %s;'
    cursor.execute(query, (limit,))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows