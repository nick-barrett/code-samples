from sqlmodel import SQLModel, create_engine
from . import models

engine = create_engine("sqlite://")

if __name__ == "__main__":
    SQLModel.metadata.create_all(engine)
