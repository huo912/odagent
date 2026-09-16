"""文档落盘保障模块（Document Writer）。

背景：各 Agent 在执行过程中倾向于把文档正文通过 `save_memory` 保存到记忆，
而最终输出（会被 CrewAI 的 output_file 机制写入 .md 文件）往往只是一段
"步骤完成 / 已保存记忆" 的过程性确认，导致 output/*.md 里没有真正的文档正文。

本模块提供兜底机制：在 Crew 运行结束后，检查每个 Agent 对应的输出文件，
若发现文件内容只是过程性确认（而非真正的文档正文），则从该 Agent 的记忆中
按章节顺序重组完整文档正文并落盘，确保所有文档都真正写到磁盘。

存储位置：<output>/<output_file>
"""

from __future__ import annotations

import re
from pathlib import Path

from odagent.memory import get_memory_store

# 统一输出目录：odagent/output（与 crew.py / server.py 一致）
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

# 每个 Agent 的输出文件与用于重组文档正文的记忆 key（按文档章节顺序）。
# 若某个 key 不存在或内容为空，则跳过该 key。
AGENT_DOCS: dict[str, dict] = {
    "requirements_analyst": {
        "output_file": "requirements_analysis.md",
        "keys": [
            "device_mgmt_ch1_final",
            "device_mgmt_ch2_user_stories",
            "device_mgmt_ch3_functional_requirements_v2",
            "device_mgmt_ch4_nonfunctional_requirements_v2",
            "device_mgmt_ch5_scope_boundaries",
            "device_mgmt_ch6_acceptance_criteria_v2",
            "device_mgmt_ch7_dependencies_risks",
            "device_mgmt_ch8_open_questions",
        ],
    },
    "software_architect": {
        "output_file": "software_architecture.md",
        "keys": [
            "chapter1_arch_scope_done",
            "chapter2_quality_attributes_done",
            "chapter3_architecture_boundary_done",
            "chapter4_module_division_done",
            "chapter5_process_dataflow_done",
            "chapter6_api_datamodel_done",
            "chapter7_tech_selection_done",
            "chapter8_security_perf_reliability_observability_done",
            "chapter9_deployment_implementation_done",
            "chapter10_risks_pending_issues",
        ],
    },
    "database_analyst": {
        "output_file": "database_design.md",
        "keys": [
            "db_design_assumptions",
            "db_entity_catalog",
            "db_entity_relationships",
            "db_type_selection",
            "db_scale_assumptions",
            "db_access_patterns",
            "db_scaling_cache_design",
            "db_backup_lifecycle_design",
            "db_field_dictionary_all_core_entities",
            "db_constraint_index_matrix",
            "db_pagination_query_optimization",
            "db_transaction_boundaries",
            "db_idempotency_concurrency",
            "db_init_migration",
            "db_security_audit_design",
        ],
    },
    "senior_fullstack_engineer": {
        "output_file": "fullstack_code.md",
        "keys": ["fullstack_deliverable"],
    },
    "senior_software_test_engineer": {
        "output_file": "software_test_plan.md",
        "keys": ["final_test_plan_document"],
    },
}

# 过程性确认的典型开头标记（用于判断文件内容是否为真正的文档正文）
_PROCESS_MARKERS = (
    "## 步骤完成",
    "## 已完成",
    "步骤完成",
    "已完成的工作",
    "已保存记忆",
    "执行确认",
    "DONE",
)


def _looks_like_process_confirmation(content: str) -> bool:
    """判断内容是否只是过程性确认而非真正的文档正文。"""
    stripped = content.strip()
    if not stripped:
        return True
    # 长度过短，几乎不可能是完整文档正文
    if len(stripped) < 300:
        return True
    # 以过程性确认标记开头
    head = stripped[:200]
    if any(marker in head for marker in _PROCESS_MARKERS):
        return True
    # 真正的文档正文通常包含 Markdown 标题
    if not re.search(r"^#{1,6}\s", stripped, flags=re.MULTILINE):
        return True
    return False


def _reconstruct_body(agent_key: str, keys: list[str]) -> str:
    """按顺序从记忆重组文档正文。"""
    store = get_memory_store()
    memories = {m.get("key"): m.get("content", "") for m in store.all(agent_key)}
    parts = []
    for key in keys:
        content = memories.get(key, "").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts).strip()


def ensure_document_on_disk(agent_key: str) -> Path | None:
    """确保指定 Agent 的文档正文已落盘。

    若输出文件不存在、或内容只是过程性确认，则尝试从记忆重组正文并写入。
    返回写入/确认的文件路径；若无法重组则返回 None。
    """
    spec = AGENT_DOCS.get(agent_key)
    if not spec:
        return None
    output_file = OUTPUT_DIR / spec["output_file"]

    # 若文件已存在且是真正的文档正文，则无需处理
    if output_file.exists():
        existing = output_file.read_text(encoding="utf-8")
        if not _looks_like_process_confirmation(existing):
            return output_file

    # 从记忆重组正文
    body = _reconstruct_body(agent_key, spec["keys"])
    if len(body) < 300:
        # 无法重组出有效正文，保留原文件（若有）
        return output_file if output_file.exists() else None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file.write_text(body + "\n", encoding="utf-8")
    return output_file


def ensure_all_documents_on_disk(agent_keys: list[str] | None = None) -> dict[str, Path | None]:
    """确保所有（或指定）Agent 的文档正文已落盘。"""
    if agent_keys is None:
        agent_keys = list(AGENT_DOCS.keys())
    result: dict[str, Path | None] = {}
    for key in agent_keys:
        result[key] = ensure_document_on_disk(key)
    return result
