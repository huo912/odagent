"""MLflow 追踪模块。

将每个 Agent/Task 的执行过程记录到 MLflow，用于可视化监控：
- Token 消耗（prompt / completion / reasoning / total）
- 执行耗时（elapsed）
- 工具调用次数（tool_calls）
- 请求次数（successful_requests）
- 执行步数（current_step / total_steps）

默认使用本地文件存储（mlruns 目录），无需额外启动 MLflow Server。
可通过环境变量覆盖：
- MLFLOW_TRACKING_URI：追踪服务地址（默认 file:./mlruns）
- MLFLOW_EXPERIMENT_NAME：实验名称（默认 odagent）
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import mlflow
from mlflow.entities import Metric

# 项目根目录（odagent/odagent）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 默认使用 SQLite 后端（MLflow 3.x 已弃用文件存储），无需额外启动服务
DEFAULT_TRACKING_URI = f"sqlite:///{PROJECT_ROOT / 'mlflow.db'}"

# 全局实验 ID 缓存
_experiment_id: str | None = None


def _ensure_experiment() -> str:
    """确保实验存在并返回实验 ID。"""
    global _experiment_id
    if _experiment_id is not None:
        return _experiment_id
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI))
    experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "odagent")
    exp = mlflow.get_experiment_by_name(experiment_name)
    if exp is None:
        exp_id = mlflow.create_experiment(experiment_name)
    else:
        exp_id = exp.experiment_id
    _experiment_id = exp_id
    return exp_id


def start_run(run_id: str, agent_name: str, role: str, requirement: str = "") -> str:
    """为单个 Agent 启动一个 MLflow run，返回 mlflow run_id。

    使用 run_name 便于在 UI 中区分（如 "需求分析师"）。
    """
    exp_id = _ensure_experiment()
    run = mlflow.start_run(
        experiment_id=exp_id,
        run_name=f"{role or agent_name}",
        nested=False,
    )
    mlflow.log_params(
        {
            "agent_key": agent_name,
            "agent_role": role or agent_name,
            "run_id": run_id,
            "requirement": (requirement or "")[:200],
        }
    )
    return run.info.run_id


def log_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    """记录一组指标到当前 run。"""
    if not metrics:
        return
    mlflow.log_metrics(metrics, step=step)


def log_metric(name: str, value: float, step: int | None = None) -> None:
    mlflow.log_metric(name, value, step=step)


def end_run(status: str = "FINISHED") -> None:
    """结束当前 run。status: FINISHED / FAILED / KILLED。"""
    try:
        mlflow.end_run(status=status)
    except Exception:
        pass


def log_agent_snapshot(
    run_id: str,
    agent_name: str,
    role: str,
    snapshot: dict[str, Any],
    requirement: str = "",
) -> str:
    """便捷方法：启动 run 并记录一次完整快照指标。

    返回 mlflow run_id。
    """
    mlflow_run_id = start_run(run_id, agent_name, role, requirement)
    log_metrics(
        {
            "total_tokens": float(snapshot.get("total_tokens", 0)),
            "prompt_tokens": float(snapshot.get("prompt_tokens", 0)),
            "completion_tokens": float(snapshot.get("completion_tokens", 0)),
            "reasoning_tokens": float(snapshot.get("reasoning_tokens", 0)),
            "successful_requests": float(snapshot.get("successful_requests", 0)),
            "tool_calls": float(snapshot.get("tool_calls", 0)),
            "elapsed": float(snapshot.get("elapsed", 0)),
            "current_step": float(snapshot.get("current_step", 0)),
            "total_steps": float(snapshot.get("total_steps", 0)),
        }
    )
    return mlflow_run_id


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """列出最近执行的 Agent runs，供前端可视化面板使用。

    返回按 start_time 倒序的 run 列表，包含指标与参数。
    """
    exp_id = _ensure_experiment()
    runs = mlflow.search_runs(
        experiment_ids=[exp_id],
        order_by=["start_time DESC"],
        max_results=limit,
    )
    result: list[dict[str, Any]] = []
    for _, row in runs.iterrows():
        result.append(
            {
                "mlflow_run_id": row.get("run_id", ""),
                "name": row.get("tags.mlflow.runName", ""),
                "status": row.get("status", ""),
                "start_time": _to_epoch_ms(row.get("start_time")),
                "params": {
                    "agent_key": row.get("params.agent_key", ""),
                    "agent_role": row.get("params.agent_role", ""),
                    "run_id": row.get("params.run_id", ""),
                    "requirement": row.get("params.requirement", ""),
                },
                "metrics": {
                    "total_tokens": _to_float(row.get("metrics.total_tokens")),
                    "prompt_tokens": _to_float(row.get("metrics.prompt_tokens")),
                    "completion_tokens": _to_float(
                        row.get("metrics.completion_tokens")
                    ),
                    "reasoning_tokens": _to_float(
                        row.get("metrics.reasoning_tokens")
                    ),
                    "successful_requests": _to_float(
                        row.get("metrics.successful_requests")
                    ),
                    "tool_calls": _to_float(row.get("metrics.tool_calls")),
                    "elapsed": _to_float(row.get("metrics.elapsed")),
                    "current_step": _to_float(row.get("metrics.current_step")),
                    "total_steps": _to_float(row.get("metrics.total_steps")),
                },
            }
        )
    return result


def _to_float(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_epoch_ms(v: Any) -> int:
    """将 pandas Timestamp 转为 epoch 毫秒。"""
    if v is None:
        return 0
    try:
        return int(v.timestamp() * 1000)
    except AttributeError:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
