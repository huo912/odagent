"""记忆系统（Memory System）。

为每个 Agent 提供跨运行的持久化记忆：
- 将 Agent 在任务中产生的关键决策、约束、经验教训保存到磁盘（JSON）。
- 下次运行时，将历史记忆注入 Agent 的 backstory / 系统提示，使其"记得"之前的上下文。
- 提供 CrewAI 工具（save_memory / retrieve_memory），让 Agent 在执行过程中主动读写记忆。

存储位置：<output>/memory/<agent_key>.json
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from crewai.tools import tool

# 记忆存储根目录：odagent/output/memory
MEMORY_DIR = Path(__file__).resolve().parents[2] / "output" / "memory"

# 每个 Agent 注入到提示中的最大记忆条数（避免上下文过长）
MAX_CONTEXT_MEMORIES = 20


class MemoryStore:
    """线程安全的记忆存储，按 Agent 持久化到 JSON 文件。"""

    def __init__(self, base_dir: Path = MEMORY_DIR) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self, agent_key: str) -> Path:
        return self._base_dir / f"{agent_key}.json"

    def _load(self, agent_key: str) -> list[dict[str, Any]]:
        f = self._file(agent_key)
        if not f.exists():
            return []
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, agent_key: str, memories: list[dict[str, Any]]) -> None:
        f = self._file(agent_key)
        f.write_text(
            json.dumps(memories, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save(
        self,
        agent_key: str,
        key: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """保存一条记忆。若 key 已存在则覆盖更新。"""
        with self._lock:
            memories = self._load(agent_key)
            entry = {
                "key": key,
                "content": content,
                "metadata": metadata or {},
                "timestamp": time.time(),
            }
            # 覆盖同 key 的旧记忆
            for i, m in enumerate(memories):
                if m.get("key") == key:
                    memories[i] = entry
                    self._save(agent_key, memories)
                    return
            memories.append(entry)
            self._save(agent_key, memories)

    def get(self, agent_key: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            for m in self._load(agent_key):
                if m.get("key") == key:
                    return m
        return None

    def search(self, agent_key: str, query: str) -> list[dict[str, Any]]:
        """按关键词模糊检索记忆（简单子串匹配）。"""
        q = query.lower()
        with self._lock:
            return [
                m
                for m in self._load(agent_key)
                if q in m.get("content", "").lower()
                or q in m.get("key", "").lower()
            ]

    def all(self, agent_key: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._load(agent_key)

    def delete(self, agent_key: str, key: str) -> bool:
        with self._lock:
            memories = self._load(agent_key)
            new_memories = [m for m in memories if m.get("key") != key]
            if len(new_memories) == len(memories):
                return False
            self._save(agent_key, new_memories)
            return True

    def clear(self, agent_key: str) -> None:
        with self._lock:
            self._save(agent_key, [])

    def to_context(self, agent_key: str, limit: int = MAX_CONTEXT_MEMORIES) -> str:
        """将历史记忆格式化为可注入提示的上下文文本。"""
        memories = self._load(agent_key)
        if not memories:
            return ""
        # 按时间倒序，取最近 limit 条
        recent = sorted(memories, key=lambda m: m.get("timestamp", 0), reverse=True)[
            :limit
        ]
        lines = ["【历史记忆】以下是你在之前任务中积累的经验与决策，请参考："]
        for m in recent:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("timestamp", 0)))
            lines.append(f"- [{m.get('key', '')}] ({ts}) {m.get('content', '')}")
        return "\n".join(lines)


# 全局单例，供工具与 Agent 注入共享
_store: MemoryStore | None = None
_store_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = MemoryStore()
        return _store


def build_memory_context(agent_key: str) -> str:
    """返回注入到 Agent backstory 的历史记忆上下文文本（无记忆时返回空串）。"""
    return get_memory_store().to_context(agent_key)


def get_memory_tools(agent_key: str) -> list[Any]:
    """返回绑定到指定 Agent 的记忆读写工具。"""
    store = get_memory_store()

    @tool("save_memory")
    def save_memory(key: str, content: str) -> str:
        """保存一条记忆。key 为记忆的简短标识（如 'tech_decision'），content 为记忆内容。"""
        store.save(agent_key, key, content)
        return f"已保存记忆 [{key}]"

    @tool("retrieve_memory")
    def retrieve_memory(query: str) -> str:
        """检索与 query 相关的历史记忆，返回匹配的记忆内容列表。"""
        results = store.search(agent_key, query)
        if not results:
            return "未找到相关记忆。"
        return "\n".join(
            f"- [{m.get('key', '')}] {m.get('content', '')}" for m in results
        )

    return [save_memory, retrieve_memory]
