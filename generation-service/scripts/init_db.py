"""初始化数据库：建表 + 种子模型。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generation.core.db import Base, SessionLocal, engine
from src.generation.services.model_service import seed_models

if __name__ == "__main__":
    import src.generation.models  # noqa: F401

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_models(db)
        print("generation db initialized with seed models")
    finally:
        db.close()
