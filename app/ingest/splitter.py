# app/ingest/splitter.py


class TextSplitter:
    """按段落聚合切片；超长段落硬切并保留 overlap。"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        chunks: list[str] = []
        buf = ""
        for para in paragraphs:
            if len(para) > self.chunk_size:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(self._hard_cut(para))
                continue
            if buf and len(buf) + len(para) + 1 > self.chunk_size:
                chunks.append(buf)
                buf = para
            else:
                buf = f"{buf}\n{para}" if buf else para
        if buf:
            chunks.append(buf)
        return chunks

    def _hard_cut(self, para: str) -> list[str]:
        step = self.chunk_size - self.chunk_overlap
        chunks: list[str] = []
        i = 0
        while i < len(para):
            if i + self.chunk_size >= len(para):
                chunks.append(para[i:])
                break
            chunks.append(para[i : i + self.chunk_size])
            i += step
        return chunks
