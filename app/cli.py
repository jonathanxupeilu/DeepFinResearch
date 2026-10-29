# app/cli.py
"""终端问答入口：python -m app.cli"""

import sys

from pydantic import ValidationError

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
        try:
            result = pipeline.answer(question)
        except KeyboardInterrupt:
            output("已中断，继续。")
            continue
        except Exception as e:  # noqa: BLE001
            output(f"⚠️ 出错了：{e}")
            continue
        output(format_answer(result))


def main() -> int:
    try:
        pipeline = build_pipeline()
    except ValidationError:
        print(
            "缺少必需的 API Key，请复制 .env.example 为 .env 并填入 "
            "DEEPSEEK_API_KEY / DASHSCOPE_API_KEY"
        )
        return 1
    run(pipeline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
