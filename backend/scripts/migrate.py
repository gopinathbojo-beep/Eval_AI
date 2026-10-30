"""Apply versioned schema migrations using the configured database."""
from app.database import migrate_database

if __name__ == "__main__":
    migrate_database()
    print("Database migrations applied.")
