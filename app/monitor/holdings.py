# app/monitor/holdings.py
import json
from pathlib import Path

from pydantic import BaseModel


class Holding(BaseModel):
    code: str
    name: str = ""


def load_holdings(path: Path = Path("config/holdings.json")) -> list[Holding]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Holding.model_validate(x) for x in data]
