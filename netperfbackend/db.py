from sqlmodel import SQLModel, create_engine
from . import models  # noqa: F401

sqlite_engine = create_engine("sqlite://")

def db_create_all():
    SQLModel.metadata.create_all(sqlite_engine)

if __name__ == "__main__":
    db_create_all()
