import psycopg2


def get_tables(db_connection):
    """Get tables"""

    # Connect to database and fetch table names
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


def get_enums(db_connection):
    """Get enum types in the schema together with values and usage columns."""

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
            t.typname AS enum_name,
            e.enumlabel AS enum_value,
            e.enumsortorder AS enum_order
        FROM pg_type t
        JOIN pg_enum e
          ON t.oid = e.enumtypid
        JOIN pg_namespace n
          ON n.oid = t.typnamespace
        WHERE n.nspname = %s
        ORDER BY t.typname, e.enumsortorder;
        """,
        (db_connection.schema,),
    )
    enum_rows = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            c.table_name,
            c.column_name,
            c.udt_name
        FROM information_schema.columns c
        JOIN pg_type t
          ON t.typname = c.udt_name
        JOIN pg_namespace n
          ON n.oid = t.typnamespace
         AND n.nspname = c.udt_schema
        WHERE c.table_schema = %s
          AND t.typtype = 'e'
        ORDER BY c.udt_name, c.table_name, c.column_name;
        """,
        (db_connection.schema,),
    )
    usage_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    enums_by_name = {}
    for enum_name, enum_value, _enum_order in enum_rows:
        enum_info = enums_by_name.setdefault(
            enum_name,
            {
                "enum_name": enum_name,
                "values": [],
                "usages": [],
            },
        )
        enum_info["values"].append(enum_value)

    for table_name, column_name, enum_name in usage_rows:
        enum_info = enums_by_name.setdefault(
            enum_name,
            {
                "enum_name": enum_name,
                "values": [],
                "usages": [],
            },
        )
        enum_info["usages"].append(
            {
                "table_name": table_name,
                "column_name": column_name,
            }
        )

    return [enums_by_name[name] for name in sorted(enums_by_name)]


def get_table_relationships(db_connection, selected_tables=None):
    """Get foreign-key relationships for the selected tables."""

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
            tc.constraint_name,
            kcu.table_name AS from_table,
            ccu.table_name AS to_table,
            kcu.column_name AS from_column,
            ccu.column_name AS to_column,
            kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = %s
          AND tc.constraint_type = 'FOREIGN KEY'
        ORDER BY kcu.table_name, tc.constraint_name, kcu.ordinal_position;
        """,
        (db_connection.schema,),
    )
    fk_rows = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS columns
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = %s
          AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type;
        """,
        (db_connection.schema,),
    )
    unique_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    selected_tables = set(selected_tables or [])

    unique_sets_by_table = {}
    primary_key_by_table = {}
    for table_name, _constraint_name, constraint_type, columns in unique_rows:
        normalized_columns = tuple(columns)
        unique_sets_by_table.setdefault(table_name, set()).add(normalized_columns)
        if constraint_type == "PRIMARY KEY":
            primary_key_by_table[table_name] = normalized_columns

    grouped_constraints = {}
    for constraint_name, from_table, to_table, from_column, to_column, _ordinal in fk_rows:
        if selected_tables and (from_table not in selected_tables or to_table not in selected_tables):
            continue

        relationship = grouped_constraints.setdefault(
            constraint_name,
            {
                "constraint_name": constraint_name,
                "from_table": from_table,
                "to_table": to_table,
                "from_columns": [],
                "to_columns": [],
            },
        )
        relationship["from_columns"].append(from_column)
        relationship["to_columns"].append(to_column)

    relationships = []
    for relationship in grouped_constraints.values():
        from_columns = tuple(relationship["from_columns"])
        is_unique_on_source = from_columns in unique_sets_by_table.get(
            relationship["from_table"],
            set(),
        )

        if is_unique_on_source:
            relationship_type = "one_to_one"
            reverse_relationship_type = "one_to_one"
            source_cardinality = "one"
            target_cardinality = "one"
        else:
            relationship_type = "many_to_one"
            reverse_relationship_type = "one_to_many"
            source_cardinality = "many"
            target_cardinality = "one"

        relationships.append(
            {
                **relationship,
                "relationship_type": relationship_type,
                "reverse_relationship_type": reverse_relationship_type,
                "source_cardinality": source_cardinality,
                "target_cardinality": target_cardinality,
                "is_bridge_table": False,
            }
        )

    outgoing_by_table = {}
    for relationship in relationships:
        outgoing_by_table.setdefault(relationship["from_table"], []).append(relationship)

    derived_many_to_many = []
    for bridge_table, outgoing_relationships in outgoing_by_table.items():
        if len(outgoing_relationships) != 2:
            continue

        related_tables = {rel["to_table"] for rel in outgoing_relationships}
        bridge_key = primary_key_by_table.get(bridge_table)
        unique_sets = unique_sets_by_table.get(bridge_table, set())
        fk_columns = tuple(
            column
            for rel in outgoing_relationships
            for column in rel["from_columns"]
        )

        if len(related_tables) != 2:
            continue

        if not any(set(unique_set) == set(fk_columns) for unique_set in unique_sets):
            continue

        if bridge_key and set(bridge_key) != set(fk_columns):
            continue

        left, right = outgoing_relationships
        left["is_bridge_table"] = True
        right["is_bridge_table"] = True

        derived_many_to_many.append(
            {
                "constraint_name": f"{bridge_table}__many_to_many",
                "from_table": left["to_table"],
                "to_table": right["to_table"],
                "from_columns": left["to_columns"],
                "to_columns": right["to_columns"],
                "through_table": bridge_table,
                "through_columns": fk_columns,
                "relationship_type": "many_to_many",
                "reverse_relationship_type": "many_to_many",
                "source_cardinality": "many",
                "target_cardinality": "many",
                "is_bridge_table": False,
                "is_derived": True,
            }
        )

    return relationships + derived_many_to_many
