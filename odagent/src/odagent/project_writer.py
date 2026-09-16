"""工程落地工具。

从全栈工程师输出的 Markdown 交付物中解析出代码文件，
并写入到标准化的工程目录结构：
  <output_root>/
    backend/     # Spring Boot 后端工程
    frontend/    # Vue3 + ElementPlus 前端工程
    sql/         # 数据库脚本
    test/        # 自动化测试代码（Playwright E2E 等）
    docs/        # 设计文档
"""

from __future__ import annotations

import re
from pathlib import Path

# 常见代码围栏语言标记
_FENCE_LANGS = {
    "java", "xml", "yaml", "yml", "properties", "sql", "vue", "js", "ts",
    "javascript", "typescript", "json", "html", "css", "scss", "less",
    "pom", "gradle", "sh", "bash", "dockerfile", "docker", "ini", "conf",
    "md", "markdown", "txt", "env", "gitignore", "kt", "kts",
    "python", "py", "spec", "feature",
}


def _is_code_fence(lang: str) -> bool:
    """判断围栏语言是否属于代码（排除纯文本/说明性语言）。"""
    lang = lang.strip().lower()
    if not lang:
        return False
    if lang in ("text", "txt", "plaintext", "console", "output", "log"):
        return False
    return True


def _extract_file_blocks(markdown: str) -> list[tuple[str, str]]:
    """从 Markdown 中提取 (文件路径, 代码内容) 列表。

    支持两种格式：
    1. 标题 + 代码块：```java\n// path: src/main/java/...\n...```
    2. 代码块首行注释标注路径：```java\n// src/main/java/...\n```
    """
    blocks: list[tuple[str, str]] = []
    # 匹配代码围栏
    fence_re = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
    for m in fence_re.finditer(markdown):
        lang = m.group(1).strip()
        body = m.group(2)
        if not _is_code_fence(lang):
            continue
        path = _find_path_in_block(lang, body)
        if path:
            blocks.append((path, body))
    return blocks


def _find_path_in_block(lang: str, body: str) -> str | None:
    """在代码块中查找文件路径标注。"""
    lines = body.splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    # 支持 // path: xxx 或 # path: xxx 或 <!-- path: xxx --> 或 /* path: xxx */
    path_match = re.search(
        r"(?:path|file|文件)\s*[:：]\s*([^\s]+)", first, re.IGNORECASE
    )
    if path_match:
        return path_match.group(1).strip("`\"'<>")
    # 支持首行直接是路径，如 // src/main/java/... 或 # src/main/java/... 或 -- sql/xxx.sql
    # 或 /* tests/xxx.js */（块注释）
    direct = re.match(
        r"^(?://|#|--|<!--|/\*)\s*([\w./\\-]+\.\w+)\s*(?:-->|\*/)?$", first
    )
    if direct:
        return direct.group(1).strip()
    return None


def _sanitize_path(path: str) -> str:
    """清理路径，防止路径穿越。"""
    path = path.replace("\\", "/").lstrip("/")
    # 移除危险片段
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def _classify(path: str) -> str:
    """根据路径判断归属目录：backend / frontend / sql / test / docs。"""
    p = path.lower()
    if p.endswith(".sql"):
        return "sql"
    # 后端特征（含后端单元测试 src/test/java）
    if any(k in p for k in (
        "src/main/java", "src/main/resources", "src/test/java",
        "pom.xml", "application.yml", "application.yaml", "application.properties",
        "backend/", "com/", "org/", "controller", "service", "mapper", "entity",
        "dto", "repository", "config/", "security",
    )):
        return "backend"
    # 测试代码特征（Playwright E2E、pytest、前端测试等）
    if any(k in p for k in (
        "tests/", "test/", "e2e/", "playwright", "spec.ts", "spec.js",
        "test_", "_test.", "conftest.py", "pytest", "cypress",
    )):
        return "test"
    # 前端特征
    if any(k in p for k in (
        "src/views", "src/components", "src/router", "src/store", "src/api",
        "src/assets", "package.json", "vite.config", "vue.config",
        "frontend/", ".vue", ".js", ".ts", ".scss", ".css", "index.html",
        "src/main.js", "src/main.ts", "src/App.vue",
    )):
        return "frontend"
    return "docs"


def write_project(markdown: str, output_root: str | Path) -> dict[str, int]:
    """将 Markdown 交付物落地为工程目录。

    返回统计信息 {backend, frontend, sql, test, docs} 各写入的文件数。
    """
    root = Path(output_root)
    stats = {"backend": 0, "frontend": 0, "sql": 0, "test": 0, "docs": 0}
    blocks = _extract_file_blocks(markdown)
    written: set[str] = set()

    for path, content in blocks:
        safe = _sanitize_path(path)
        if not safe or safe in written:
            continue
        category = _classify(safe)
        rel = _rel_to_category(safe, category)
        target = root / category / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # 去除代码块首行的路径标注注释
        cleaned = _strip_path_annotation(content)
        target.write_text(cleaned, encoding="utf-8")
        written.add(safe)
        stats[category] += 1

    return stats


def _strip_path_annotation(content: str) -> str:
    """移除代码内容首行的路径标注注释。"""
    lines = content.splitlines()
    if not lines:
        return content
    first = lines[0].strip()
    if re.search(r"(?:path|file|文件)\s*[:：]", first, re.IGNORECASE):
        return "\n".join(lines[1:]).lstrip("\n")
    if re.match(r"^(?://|#|<!--|/\*)\s*[\w./\\-]+\.\w+\s*(?:-->|\*/)?$", first):
        return "\n".join(lines[1:]).lstrip("\n")
    return content


# 各分类目录的路径前缀（用于去除重复嵌套）
_CATEGORY_PREFIXES = {
    "backend": ("backend/",),
    "frontend": ("frontend/", "web/"),
    "test": ("test/", "tests/", "e2e/"),
    "sql": ("sql/",),
}


def _rel_to_category(path: str, category: str) -> str:
    """将路径转换为相对分类目录的路径，去除已包含的分类前缀。

    例如：
      backend/src/main/java/...  + backend -> src/main/java/...
      backend/pom.xml           + backend -> pom.xml
      frontend/src/App.vue      + frontend -> src/App.vue
      tests/e2e/login.spec.js   + test     -> e2e/login.spec.js
      backend/sql/init.sql      + sql      -> init.sql
    """
    p = path
    for prefix in _CATEGORY_PREFIXES.get(category, ()):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    # sql 特殊处理：backend/sql/init.sql -> 去掉 backend/ 后仍含 sql/，再去掉
    if category == "sql":
        # 去掉可能存在的 backend/ 前缀
        if p.startswith("backend/"):
            p = p[len("backend/"):]
        if p.startswith("sql/"):
            p = p[len("sql/"):]
    return p
