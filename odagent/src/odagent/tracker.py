"""进度与 Token 使用量追踪器。

负责记录每个 Agent 的执行状态、耗时、Token 使用量，并支持
通过回调函数将实时进度推送给可视化前端（WebSocket / SSE）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from crewai import Agent, TaskOutput


@dataclass
class AgentProgress:
    """单个 Agent 的进度信息。"""

    name: str
    role: str
    status: str = "pending"  # pending / running / completed / failed
    started_at: float | None = None
    finished_at: float | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    successful_requests: int = 0
    message: str = ""
    output_file: str = ""
    # 进度相关：当前已执行步数与预估总步数（用于计算进度百分比）
    current_step: int = 0
    total_steps: int = 0
    # 工具调用次数（用于定位工具调用过于频繁的 Agent）
    tool_calls: int = 0

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)


class ProgressTracker:
    """线程安全的进度追踪器，维护所有 Agent 的状态并广播变更。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, AgentProgress] = {}
        self._order: list[str] = []
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._run_id: str = ""
        self._requirement: str = ""
        self._overall_status: str = "pending"
        # 缓存 Agent 实例，用于 step_callback 中读取实时 token
        self._agent_instances: dict[str, Agent] = {}
        # 暂停/继续控制：记录被暂停的 Agent，以及每个 Agent 的恢复事件
        self._paused: set[str] = set()
        self._pause_events: dict[str, threading.Event] = {}

    # ---- 监听器 ----
    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _broadcast(self) -> None:
        snapshot = self.snapshot()
        listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                # 单个监听器失败不影响主流程
                pass

    # ---- 状态管理 ----
    def start_run(self, run_id: str, requirement: str) -> None:
        with self._lock:
            self._run_id = run_id
            self._requirement = requirement
            self._overall_status = "running"
        self._broadcast()

    def register_agent(self, name: str, role: str) -> None:
        with self._lock:
            if name not in self._agents:
                self._agents[name] = AgentProgress(name=name, role=role)
                self._order.append(name)
        self._broadcast()

    def set_total_steps(self, name: str, total_steps: int) -> None:
        """设置 Agent 的预估总步数（用于计算进度百分比）。"""
        with self._lock:
            if name not in self._agents:
                return
            self._agents[name].total_steps = max(0, int(total_steps))
        self._broadcast()

    def register_agent_instance(self, name: str, agent: Agent) -> None:
        """缓存 Agent 实例，供 step_callback 读取实时 token 使用。"""
        with self._lock:
            self._agent_instances[name] = agent

    def update_usage_from_agent(self, name: str) -> None:
        """从缓存的 Agent 实例读取实时 token 使用量。"""
        with self._lock:
            agent = self._agent_instances.get(name)
            if agent is None:
                return
            try:
                usage = agent._current_usage_summary()  # type: ignore[attr-defined]
            except Exception:
                return
            if name not in self._agents:
                return
            ap = self._agents[name]
            ap.total_tokens = getattr(usage, "total_tokens", 0)
            ap.prompt_tokens = getattr(usage, "prompt_tokens", 0)
            ap.completion_tokens = getattr(usage, "completion_tokens", 0)
            ap.reasoning_tokens = getattr(usage, "reasoning_tokens", 0)
            ap.successful_requests = getattr(usage, "successful_requests", 0)
        self._broadcast()

    def mark_running(self, name: str, message: str = "") -> None:
        with self._lock:
            if name not in self._agents:
                self.register_agent(name, "")
            self._agents[name].status = "running"
            self._agents[name].started_at = self._agents[name].started_at or time.time()
            self._agents[name].message = message
            # 每执行一步（step_callback 触发）递增当前步数
            self._agents[name].current_step += 1
        self._broadcast()

    def increment_tool_calls(self, name: str) -> None:
        """递增指定 Agent 的工具调用次数。"""
        with self._lock:
            if name not in self._agents:
                return
            self._agents[name].tool_calls += 1
        self._broadcast()

    def mark_all_running(self) -> None:
        """将尚未开始的 Agent 标记为运行中（用于顺序执行时提前展示）。

        注意：此处不设置 started_at，真正的开始时间由 step_callback
        在 Agent 首次执行时通过 mark_running 记录，从而保证每个 Agent
        的耗时是独立、准确的，而不是从 kickoff 开始累加。
        """
        with self._lock:
            for name, agent in self._agents.items():
                if agent.status == "pending":
                    agent.status = "running"
        self._broadcast()

    def mark_completed(self, name: str, output_file: str = "") -> None:
        with self._lock:
            if name not in self._agents:
                return
            self._agents[name].status = "completed"
            self._agents[name].finished_at = time.time()
            self._agents[name].output_file = output_file
        self._broadcast()

    def mark_failed(self, name: str, message: str = "") -> None:
        with self._lock:
            if name not in self._agents:
                return
            self._agents[name].status = "failed"
            self._agents[name].finished_at = time.time()
            self._agents[name].message = message
        self._broadcast()

    def update_usage(self, name: str, usage: Any) -> None:
        """从 UsageMetrics 更新 token 使用量。"""
        with self._lock:
            if name not in self._agents:
                return
            agent = self._agents[name]
            agent.total_tokens = getattr(usage, "total_tokens", 0)
            agent.prompt_tokens = getattr(usage, "prompt_tokens", 0)
            agent.completion_tokens = getattr(usage, "completion_tokens", 0)
            agent.reasoning_tokens = getattr(usage, "reasoning_tokens", 0)
            agent.successful_requests = getattr(usage, "successful_requests", 0)
        self._broadcast()

    def finish_run(self, success: bool = True) -> None:
        with self._lock:
            self._overall_status = "completed" if success else "failed"
        self._broadcast()

    # ---- 暂停 / 继续控制 ----
    def pause_agent(self, name: str) -> None:
        """暂停指定 Agent：设置暂停标记并创建恢复事件。"""
        with self._lock:
            self._paused.add(name)
            self._pause_events.setdefault(name, threading.Event())
            if name in self._agents:
                self._agents[name].status = "paused"
        self._broadcast()

    def resume_agent(self, name: str) -> None:
        """继续指定 Agent：清除暂停标记并触发恢复事件。"""
        with self._lock:
            self._paused.discard(name)
            event = self._pause_events.get(name)
            if event is not None:
                event.set()
            if name in self._agents and self._agents[name].status == "paused":
                self._agents[name].status = "running"
        self._broadcast()

    def is_paused(self, name: str) -> bool:
        with self._lock:
            return name in self._paused

    def wait_if_paused(self, name: str) -> None:
        """若指定 Agent 处于暂停状态，则阻塞等待直到被继续。

        在 step_callback 中调用，实现"每步之间可暂停/继续"。
        """
        while True:
            with self._lock:
                paused = name in self._paused
                event = self._pause_events.get(name)
            if not paused:
                return
            if event is not None:
                event.wait()
            else:
                # 没有事件对象时短暂等待后重查
                time.sleep(0.2)

    def clear_pause_state(self) -> None:
        """清除所有暂停状态（新任务开始时调用）。"""
        with self._lock:
            self._paused.clear()
            self._pause_events.clear()

    # ---- 查询 ----
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            agents = [
                {
                    "name": self._agents[n].name,
                    "role": self._agents[n].role,
                    "status": self._agents[n].status,
                    "elapsed": self._agents[n].elapsed,
                    "total_tokens": self._agents[n].total_tokens,
                    "prompt_tokens": self._agents[n].prompt_tokens,
                    "completion_tokens": self._agents[n].completion_tokens,
                    "reasoning_tokens": self._agents[n].reasoning_tokens,
                    "successful_requests": self._agents[n].successful_requests,
                    "message": self._agents[n].message,
                    "output_file": self._agents[n].output_file,
                    "current_step": self._agents[n].current_step,
                    "total_steps": self._agents[n].total_steps,
                    "tool_calls": self._agents[n].tool_calls,
                    "paused": n in self._paused,
                }
                for n in self._order
            ]
            total_tokens = sum(a["total_tokens"] for a in agents)
            return {
                "run_id": self._run_id,
                "requirement": self._requirement,
                "overall_status": self._overall_status,
                "total_tokens": total_tokens,
                "agents": agents,
            }


# 全局单例，供 CLI 与 Web 服务共享
_tracker: ProgressTracker | None = None


def get_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker


def make_task_callback(tracker: ProgressTracker, agent_name: str):
    """构造 CrewAI Task 的 callback，用于在任务完成后更新 token 与状态。

    CrewAI 会以 TaskOutput 作为唯一参数调用 callback。
    """

    def callback(output: TaskOutput) -> None:
        agent: Agent | None = getattr(output, "agent", None)
        if agent is not None:
            try:
                usage = agent._current_usage_summary()  # type: ignore[attr-defined]
                tracker.update_usage(agent_name, usage)
            except Exception:
                pass
        tracker.mark_completed(agent_name)

    return callback


def make_step_callback(tracker: ProgressTracker, agent_name: str):
    """构造 Agent 的 step_callback，用于在每一步执行后实时更新 token 与耗时。

    CrewAI 会以 AgentAction | AgentFinish 作为唯一参数调用 step_callback。
    通过 agent_name 关联到对应的 Agent 实例，从而读取该 Agent 独立的
    token 使用量，并记录其真实的开始时间（独立耗时）。
    """

    def callback(_step) -> None:
        # 若该 Agent 被暂停，则在此阻塞等待，直到前端点击"继续"
        tracker.wait_if_paused(agent_name)
        # 标记运行中并记录真实开始时间（仅首次）
        tracker.mark_running(agent_name)
        # 通过 tracker 中缓存的 agent 实例读取实时 token
        tracker.update_usage_from_agent(agent_name)
        # 若该步是工具调用（AgentAction），则递增工具调用计数
        try:
            from crewai.agents.crew_agent_executor import AgentAction

            if isinstance(_step, AgentAction):
                tracker.increment_tool_calls(agent_name)
        except Exception:
            pass

    return callback
