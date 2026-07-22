import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine  # get the SQL syntax to DB #

load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # app/.env, regardless of cwd

# fill the database url #
engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"options": "-c statement_timeout=5000"},  # กัน query ค้างเกิน 5 วิ
)