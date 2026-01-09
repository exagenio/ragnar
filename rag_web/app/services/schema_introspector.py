import psycopg2


def get_tables(db_connection):
    conn = psycopg2.connect(
        host=db_connection.host,
        port=db_connection.port,
        dbname=db_connection.database_name,
        user=db_connection.username,
        password=db_connection.password,
    )

    cursor = conn.cursor()

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """, (db_connection.schema,))

    tables = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return tables
