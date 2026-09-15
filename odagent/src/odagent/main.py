#!/usr/bin/env python

"""OmniDev Agent 命令行入口。

支持两种输入方式：
1. 直接输入需求文本
2. 提供 Word (.docx) / 文本 (.txt / .md) 需求文档路径

运行完成后，会将全栈工程师输出的代码落地为完整工程：
  <output_root>/
    backend/     # Spring Boot 后端
    frontend/    # Vue3 + ElementPlus 前端
    sql/         # 数据库脚本
    docs/        # 设计文档
"""

import argparse
import sys
import time
import uuid
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odagent.crew import ODAgentCrew
from odagent.docx_parser import extract_text
from odagent.project_writer import write_project
from odagent.tracker import get_tracker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "output" / "generated_project"


def _read_input(path: str | None, text: str | None) -> str:
    """读取输入：优先文档路径，其次直接文本。"""
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"需求文档不存在: {p}")
        print(f"正在解析需求文档: {p}")
        return extract_text(p)
    if text:
        return text.strip()
    raise ValueError("请提供需求文本（--text）或需求文档路径（--file）")


def run() -> None:
    parser = argparse.ArgumentParser(description="OmniDev Agent 全栈代码生成")
    parser.add_argument("--file", "-f", help="需求文档路径（.docx / .txt / .md）")
    parser.add_argument("--text", "-t", help="需求文本内容")
    parser.add_argument(
        "--output",
        "-o",
        default=str(OUTPUT_ROOT),
        help="工程输出根目录（默认 output/generated_project）",
    )
    args = parser.parse_args()

    requirement = _read_input(args.file, args.text)

    tracker = get_tracker()
    run_id = uuid.uuid4().hex[:8]
    tracker.start_run(run_id, requirement[:200])

    started_at = time.monotonic()
    print("开始执行 Crew，LLM 请求超时由 LLM_TIMEOUT_SECONDS 控制。")
    try:
        ODAgentCrew(tracker=tracker).kickoff(
            inputs={"requirement": requirement}
        )
        tracker.finish_run(success=True)
    except Exception as exc:  # noqa: BLE001
        tracker.finish_run(success=False)
        print(f"\n执行失败: {exc}")
        raise

    elapsed_seconds = time.monotonic() - started_at
    print(f"\nCrew 结束，总耗时 {elapsed_seconds:.1f} 秒。")

    # 工程落地
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    fullstack_md = PROJECT_ROOT / "output" / "fullstack_code.md"
    test_md = PROJECT_ROOT / "output" / "software_test_plan.md"
    if fullstack_md.exists():
        print(f"\n正在将代码落地到工程目录: {output_root}")
        stats = write_project(fullstack_md.read_text(encoding="utf-8"), output_root)
        print(f"全栈代码落地完成: {stats}")
    else:
        print("\n未找到 fullstack_code.md，跳过工程落地。")
    if test_md.exists():
        stats = write_project(test_md.read_text(encoding="utf-8"), output_root)
        print(f"测试代码落地完成: {stats}")


if __name__ == "__main__":
    run()
