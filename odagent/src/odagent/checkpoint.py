"""检查点机制（Checkpoint Mechanism）。

在 Crew 执行过程中，每个 Agent 任务完成后自动保存检查点（JSON），
记录已完成的任务、其输出文件路径与时间戳。当任务中断/失败后，
可基于检查点恢复：跳过已完成的任务，仅执行未完成的部分。

存储位置：<output>/checkpoints/<run_id>.json
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

# 检查点存储根目录：odagent/output/checkpoints
CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "output" / "checkpoints"


class CheckpointManager:
    """线程安全的检查点管理器，按 run_id 持久化到 JSON 文件。"""

    def __init__(self, base_dir: Path = CHECKPOINT_DIR) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self, run_id: str) -> Path:
        return self._base_dir / f"{run_id}.json"

    def _load(self, run_id: str) -> dict[str, Any]:
        f = self._file(run_id)
        if not f.exists():
            return {"run_id": run_id, "completed": {}, "created_at": time.time()}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"run_id": run_id, "completed": {}, "created_at": time.time()}

    def _save(self, data: dict[str, Any]) -> None:
        self._file(data["run_id"]).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def mark_completed(
        self,
        run_id: str,
        agent_key: str,
        output_file: str = "",
        summary: str = "",
    ) -> None:
        """记录某个 Agent 任务已完成。"""
        with self._lock:
            data = self._load(run_id)
            data["completed"][agent_key] = {
                "output_file": output_file,
                "summary": summary,
                "timestamp": time.time(),
            }
            data["updated_at"] = time.time()
            self._save(data)

    def is_completed(self, run_id: str, agent_key: str) -> bool:
        with self._lock:
            return agent_key in self._load(run_id).get("completed", {})

    def get_completed(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._load(run_id).get("completed", {})

    def get(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._load(run_id)

    def list_checkpoints(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近的检查点文件，供前端展示。"""
        if not self._base_dir.exists():
            return []
        items = []
        for f in sorted(
            self._base_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            items.append(
                {
                    "run_id": data.get("run_id", f.stem),
                    "completed": list(data.get("completed", {}).keys()),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0),
                }
            )
        return items

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._file(run_id).unlink(missing_ok=True)


# 全局单例
_manager: CheckpointManager | None = None
_manager_lock = threading.Lock()


def get_checkpoint_manager() -> CheckpointManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = CheckpointManager()
        return _manager
