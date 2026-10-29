# app/cli.py
"""终端问答入口：python -m app.cli"""

import sys

from app.factory import build_pipeline
from app.models import RagAnswer

EXIT_WORDS = {"/exit", "/quit", "exit", "quit", "q"}


def format_answer(result: RagAnswer) -> str:
    lines = [result.answer]
    if result.citations:
        lines.append("")
        lines.append("📎 引用来源:")
        lines.extend(f"  [{c.marker}] {c.source}" for c in result.citations)
    return "\n".join(lines)


def run(pipeline, input_fn=input, output=print) -> None:
    output("⚙️ DeepFinResearch 投研顾问（输入 /exit 退出）")
    while True:
        try:
            question = input_fn("❯ ").strip()
        except (EOFError, KeyboardInterrupt, StopIteration):
            # StopIteration：注入的输入源耗尽，等价于 EOF
            output("再见。")
            return
        if not question:
            continue
        if question.lower() in EXIT_WORDS:
            output("再见。")
            return
        result = pipeline.answer(question)
        output(format_answer(result))


def main() -> int:
    run(build_pipeline())
    return 0


if __name__ == "__main__":
    sys.exit(main())
