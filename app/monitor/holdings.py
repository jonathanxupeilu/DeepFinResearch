# app/monitor/holdings.py
import json
from pathlib import Path

from pydantic import BaseModel, field_validator

_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "holdings.json"


class Holding(BaseModel):
    code: str
    name: str = ""

    @field_validator("code")
    @classmethod
    def code_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code 不能为空")
        return v


def load_holdings(path: Path = _DEFAULT) -> list[Holding]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("holdings.json 必须是 JSON 数组")  # noqa: TRY004
    return [Holding.model_validate(x) for x in data]
