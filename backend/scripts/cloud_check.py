"""Read-only cloud configuration checks. Never prints credentials or raw provider errors."""
import sys
from sqlalchemy import text, inspect
from app.config import get_settings
from app.database import engine
from app.documents.cloud import SupabaseStorage
from app.ocr.remote import status


def main():
    s = get_settings()
    failed = False
    for name, check in (("PostgreSQL", lambda: database()),
                        ("Private storage bucket", lambda: bucket()),
                        ("Vision model", lambda: status())):
        try:
            result = check()
            print(f"{name}: OK {result or ''}")
        except Exception as error:
            failed = True
            print(f"{name}: FAILED ({type(error).__name__}); check the corresponding credentials/configuration.")
    return 1 if failed else 0


def database():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        return "(schema installed)" if inspect(connection).has_table("alembic_version") else "(ready for migrations)"


def bucket():
    info = SupabaseStorage().bucket_info()
    if info.get("public") is not False:
        raise ValueError("Bucket must be private")


if __name__ == "__main__":
    sys.exit(main())
