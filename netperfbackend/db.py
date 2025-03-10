from sqlmodel import SQLModel, create_engine
from . import models  # noqa: F401

engine = create_engine("sqlite://")

if __name__ == "__main__":
    SQLModel.metadata.create_all(engine)
