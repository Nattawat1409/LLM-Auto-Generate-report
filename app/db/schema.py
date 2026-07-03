from sqlalchemy import inspect

from db.engine import engine

# get real schema text from the actual database #
def get_schema_text() -> str:
    inspector = inspect(engine)
    lines = []
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        col_defs = ", ".join(f"{col['name']} {col['type']}" for col in columns)
        lines.append(f"{table_name}({col_defs})")
    return "\n".join(lines)


# test standalone function #
if __name__ == "__main__":
    print(get_schema_text())
