import psycopg2


def get_table_columns(db_connection, table_name):
    """Get table columns"""

    # Connect to database and fetch column metadata
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
            is_nullable,
            udt_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (db_connection.schema, table_name),
    )

    raw_columns = cursor.fetchall()

    enum_names = [
        udt_name
        for _name, data_type, _is_nullable, udt_name in raw_columns
        if data_type == "USER-DEFINED"
    ]
    enum_values_by_name = {}
    if enum_names:
        cursor.execute(
            """
            SELECT
                t.typname AS enum_name,
                e.enumlabel AS enum_value,
                e.enumsortorder AS enum_order
            FROM pg_type t
            JOIN pg_enum e
              ON t.oid = e.enumtypid
            JOIN pg_namespace n
              ON n.oid = t.typnamespace
            WHERE n.nspname = %s
              AND t.typname = ANY(%s)
            ORDER BY t.typname, e.enumsortorder;
            """,
            (db_connection.schema, enum_names),
        )
        for enum_name, enum_value, _enum_order in cursor.fetchall():
            enum_values_by_name.setdefault(enum_name, []).append(enum_value)

    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY';
        """,
        (db_connection.schema, table_name),
    )
    primary_key_columns = {row[0] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'UNIQUE';
        """,
        (db_connection.schema, table_name),
    )
    unique_columns = {row[0] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT
            kcu.column_name,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column,
            tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
        ORDER BY kcu.ordinal_position;
        """,
        (db_connection.schema, table_name),
    )
    foreign_keys_by_column = {}
    for column_name, referenced_table, referenced_column, constraint_name in cursor.fetchall():
        foreign_keys_by_column.setdefault(column_name, []).append(
            {
                "constraint_name": constraint_name,
                "referenced_table": referenced_table,
                "referenced_column": referenced_column,
            }
        )

    columns = []
    for name, data_type, is_nullable, udt_name in raw_columns:
        is_enum = data_type == "USER-DEFINED" and udt_name in enum_values_by_name
        enum_values = enum_values_by_name.get(udt_name, [])
        column_type = f"enum({udt_name})" if is_enum else data_type.strip('"')
        columns.append(
            {
                "name": name,
                "type": column_type,
                "data_type": data_type.strip('"'),
                "udt_name": udt_name,
                "is_enum": is_enum,
                "enum_name": udt_name if is_enum else None,
                "accepted_values": enum_values,
                "nullable": (is_nullable == "YES"),
                "is_primary_key": name in primary_key_columns,
                "is_unique": name in unique_columns or name in primary_key_columns,
                "foreign_keys": foreign_keys_by_column.get(name, []),
            }
        )

    cursor.close()
    conn.close()

    return columns
