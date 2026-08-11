"""初始化 agent 数据库。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.core.db import Base, SessionLocal, engine

if __name__ == "__main__":
    import src.agent.models  # noqa: F401

    Base.metadata.create_all(engine)
    print("agent db initialized")
