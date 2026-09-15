"""Word 需求文档解析模块。

支持将 .docx 需求文档解析为纯文本，供后续 Agent 分析使用。
同时支持 .txt / .md 等纯文本格式。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document


def extract_text_from_docx(path: str | Path) -> str:
    """从 .docx 文件中提取全部文本内容。

    会保留段落顺序，并尽量保留标题层级信息（以 # 前缀标记），
    便于 LLM 理解文档结构。
    """
    doc = Document(str(path))
    lines: list[str] = []

    # 遍历 body 元素，按文档顺序处理段落和表格
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    def iter_block_items(parent):
        from docx.oxml.ns import qn

        for child in parent.element.body.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style_name = (block.style.name or "").lower() if block.style else ""
            if "heading" in style_name:
                try:
                    level = int("".join(ch for ch in style_name if ch.isdigit()) or "1")
                except ValueError:
                    level = 1
                lines.append(f"{'#' * min(level, 6)} {text}")
            else:
                lines.append(text)
        elif isinstance(block, Table):
            lines.append("[表格]")
            for row in block.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                lines.append(" | ".join(cells))
            lines.append("[/表格]")

    return "\n".join(lines)


def extract_text(path: str | Path) -> str:
    """根据文件后缀提取文本内容。"""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".docx":
        return extract_text_from_docx(p)
    if suffix in (".txt", ".md", ".markdown"):
        return p.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"不支持的文件格式: {suffix}，请提供 .docx / .txt / .md 文件")
