# app/pipeline/citations.py
"""引用构建共享逻辑：rag（单轮）与 agent（ReAct 循环）共用。"""

import re
from collections.abc import Sequence

from app.models import Citation

_CITE_RE = re.compile(r"\[(\d+)\]")


def build_citations(reply: str, sources: Sequence[tuple[str, str]]) -> list[Citation]:
    """按 (source, text) 序列编号构建引用。

    只保留回答中实际标注 [n] 的来源；n 越界忽略；一个都没标则保留全部。
    """
    cited = {int(m) for m in _CITE_RE.findall(reply)}
    if not cited:
        return [
            Citation(marker=i + 1, source=src, text=text)
            for i, (src, text) in enumerate(sources)
        ]
    return [
        Citation(marker=i + 1, source=src, text=text)
        for i, (src, text) in enumerate(sources)
        if i + 1 in cited
    ]
