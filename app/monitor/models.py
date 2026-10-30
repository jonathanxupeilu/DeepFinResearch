# app/monitor/models.py
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Dimension(str, Enum):
    ANNOUNCEMENT = "持仓公告"
    NEWS = "每日要闻"
    MACRO = "宏观指标"
    FED = "美联储"
    POLICY = "重大会议"
    INDUSTRY = "行业指标"


class MonitorEvent(BaseModel):
    dimension: Dimension
    title: str
    source: str
    content: str = ""
    url: str = ""
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=datetime.now)

    @field_validator("title", "source")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("字段不能为空")
        return v


class CollectReport(BaseModel):
    dimension: Dimension
    ok: bool
    added: int = 0
    error: str | None = None
