#!/usr/bin/env python3
"""
进程内定时任务调度器（替代容器里的 cron）

两类触发方式：
- interval_seconds：固定间隔，可选启动后立刻跑一次（看板刷新）
- daily_times：每天固定时刻，按进程本地时区（原 crontab 的 9:00 / 15:00 告警、10:00 邮箱扫描）

所有任务在同一个后台线程里顺序执行、互不并发；单个任务抛异常只记录失败，不影响其它任务。
每次运行结果通过 on_result 回调交出去（StateManager 供 /health 与 /api/jobs 展示，Prometheus 记指标），
调度器本身不依赖它们。
"""
import threading
import time as time_module
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Callable, List, Optional

from core.logger import get_logger
from core.timeutil import describe_daily_times, local_now, next_daily_occurrence

logger = get_logger('scheduler')


@dataclass
class Job:
    """一个定时任务。interval_seconds 与 daily_times 二选一，都不填表示关闭。"""
    name: str
    run: Callable[[], Any]
    description: str = ''
    interval_seconds: Optional[int] = None
    daily_times: List[time] = field(default_factory=list)
    run_at_start: bool = False
    next_run: Optional[datetime] = None

    @property
    def enabled(self) -> bool:
        return bool(self.interval_seconds and self.interval_seconds > 0) or bool(self.daily_times)

    def schedule_text(self) -> str:
        if self.interval_seconds and self.interval_seconds > 0:
            return f'每 {self.interval_seconds} 秒'
        return describe_daily_times(self.daily_times)

    def initial_next_run(self, now: datetime) -> Optional[datetime]:
        if self.interval_seconds and self.interval_seconds > 0:
            return now if self.run_at_start else now + timedelta(seconds=self.interval_seconds)
        if self.daily_times:
            return next_daily_occurrence(now, self.daily_times)
        return None

    def following_run(self, now: datetime) -> Optional[datetime]:
        """一次运行结束后的下一次时刻"""
        if self.interval_seconds and self.interval_seconds > 0:
            return now + timedelta(seconds=self.interval_seconds)
        if self.daily_times:
            return next_daily_occurrence(now, self.daily_times)
        return None


@dataclass
class JobResult:
    name: str
    success: bool
    started_at: datetime
    duration_seconds: float
    error: Optional[str] = None
    detail: Any = None


class JobScheduler:
    """单线程顺序调度器"""

    def __init__(self, jobs: List[Job], stop_event: Optional[threading.Event] = None,
                 on_result: Optional[Callable[[Job, JobResult], None]] = None,
                 max_wait_seconds: float = 60.0):
        self.jobs = list(jobs)
        self._stop_event = stop_event or threading.Event()
        self._on_result = on_result
        self._max_wait = max_wait_seconds
        self._thread: Optional[threading.Thread] = None
        self._run_lock = threading.Lock()  # 手动触发与后台线程不并发
        now = local_now()
        for job in self.jobs:
            job.next_run = job.initial_next_run(now)

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name='job-scheduler', daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        logger.info("定时任务调度器已启动: " + ', '.join(f"{j.name}={j.schedule_text()}" for j in self.jobs))
        while not self._stop_event.is_set():
            try:
                self.run_pending()
            except Exception as e:  # 调度器自身绝不能死
                logger.error(f"调度循环异常: {e}", exc_info=True)
            self._stop_event.wait(self._seconds_until_next())
        logger.info("定时任务调度器已停止")

    def _seconds_until_next(self) -> float:
        now = local_now()
        upcoming = [j.next_run for j in self.jobs if j.enabled and j.next_run is not None]
        if not upcoming:
            return self._max_wait
        wait = (min(upcoming) - now).total_seconds()
        # 上限一分钟：时钟跳变、配置变化都能及时反应；下限防止空转
        return max(0.1, min(self._max_wait, wait))

    # ---------- 执行 ----------

    def run_pending(self, now: Optional[datetime] = None) -> List[JobResult]:
        """执行所有到点的任务，返回本轮结果"""
        now = now or local_now()
        results = []
        for job in self.jobs:
            if not job.enabled or job.next_run is None or job.next_run > now:
                continue
            results.append(self.run_job(job))
        return results

    def run_job(self, job: Job) -> JobResult:
        """立刻执行一个任务并推进它的下一次时刻（手动触发也走这里）"""
        with self._run_lock:
            started_at = local_now()
            started_clock = time_module.monotonic()
            logger.info(f"[{job.name}] 开始执行")
            try:
                detail = job.run()
                result = JobResult(job.name, True, started_at, time_module.monotonic() - started_clock, detail=detail)
                logger.info(f"[{job.name}] 执行完成，耗时 {result.duration_seconds:.2f} 秒")
            except Exception as e:
                result = JobResult(job.name, False, started_at, time_module.monotonic() - started_clock, error=str(e))
                logger.error(f"[{job.name}] 执行失败: {e}", exc_info=True)

            job.next_run = job.following_run(local_now())
            if self._on_result:
                try:
                    self._on_result(job, result)
                except Exception as e:
                    logger.error(f"[{job.name}] 记录任务结果失败: {e}", exc_info=True)
            return result
