import psycopg2


def get_table_columns(db_connection, table_name):
    """
    Returns column metadata for a given table.
    """
    conn = psycopg2.connect(
        host=db_connection.host,
        port=db_connection.port,
        dbname=db_connection.database_name,
        user=db_connection.username,
        password=db_connection.password,
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (db_connection.schema, table_name),
    )

    columns = []
    for name, data_type, is_nullable in cursor.fetchall():
        columns.append(
            {
                "name": name,
                "type": data_type.strip('"'),
                "nullable": (is_nullable == "YES"),
            }
        )

    cursor.close()
    conn.close()

    return columns
