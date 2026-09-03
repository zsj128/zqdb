# -*- coding: utf-8 -*-
"""
可观测性模块（参考 day64_observability.py）

提供两个能力：
  A. MetricsCollector —— 指标收集器：请求数 / 缓存命中率 / 降级率 / 延迟分位数
  B. log_event         —— 结构化 JSON 日志，便于后端采集与 grep 检索

设计原则：
  - 纯 Python、零额外依赖，不引入 Prometheus 也能演示
  - 埋点只在"边界处"（请求入口/出口、缓存命中、降级兜底），不侵入业务细节
"""
import time
import json
from collections import deque


class MetricsCollector:
    """单进程指标桶：请求数、命中数、降级数、最近 N 次延迟。"""

    def __init__(self, window: int = 200):
        self.total_requests = 0                  # 累计请求数（QPS 的分子）
        self.cache_hits = 0                      # 缓存命中次数
        self.errors = 0                          # 走兜底(降级)的次数
        self.degrade_breakdown = {}              # reason -> 次数，便于分析降级原因
        # 区分缓存命中/未命中分别统计延迟：
        #   _latencies_hit   —— 缓存命中（毫秒级，展示"秒回"效果）
        #   _latencies_miss  —— 真实 LLM 调用（秒级，才是真正"回答耗时"）
        self._latencies_hit = deque(maxlen=window)
        self._latencies_miss = deque(maxlen=window)

    def observe(self, *, latency_ms: float, cache_hit: bool, degraded: bool,
                degrade_reason: str = ""):
        """每次问答结束调用一次，记录一条观测。"""
        self.total_requests += 1
        if cache_hit:
            self.cache_hits += 1
            self._latencies_hit.append(latency_ms)
        else:
            self._latencies_miss.append(latency_ms)
        if degraded:
            self.errors += 1
            reason = (degrade_reason or "unknown")[:60]
            self.degrade_breakdown[reason] = self.degrade_breakdown.get(reason, 0) + 1

    @staticmethod
    def _percentile(lat, p):
        """样本足够才返回分位数，否则返回 None（前端显示'样本不足'）。"""
        if not lat:
            return None
        lat = sorted(lat)
        n = len(lat)
        # 至少 10 个样本，分位数才有统计意义
        if n < 10:
            return None
        return round(lat[min(int(n * p), n - 1)], 1)

    def _lat_stats(self, lat):
        n = len(lat)
        avg = round(sum(lat) / n, 1) if n else None
        return {
            "avg": avg,
            "p95": self._percentile(lat, 0.95),
            "p99": self._percentile(lat, 0.99),
            "sample_count": n,
        }

    def snapshot(self) -> dict:
        """导出指标快照，供 /metrics 与前端展示。

        latency 区分命中/未命中：
          - hit  缓存命中延迟（应接近毫秒级，体现缓存价值）
          - miss 真实 LLM 调用延迟（才是真正回答耗时）
        分位数在样本不足时返回 None，避免误导（如 P95=P99=max）。
        """
        hit_rate = (self.cache_hits / self.total_requests) if self.total_requests else 0.0
        err_rate = (self.errors / self.total_requests) if self.total_requests else 0.0
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(hit_rate, 3),
            "error_rate": round(err_rate, 3),
            "degrade_breakdown": self.degrade_breakdown,
            "latency_hit": self._lat_stats(self._latencies_hit),
            "latency_miss": self._lat_stats(self._latencies_miss),
        }


def log_event(level: str, event: str, **fields):
    """打印一行 JSON 日志；**fields 携带业务字段，便于检索与告警。"""
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        level = "INFO"
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "level": level,
        "event": event,
        **fields,
    }
    print(json.dumps(record, ensure_ascii=False))


# 全局单例：供 main.py / routes.py 复用
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """返回全局指标收集器单例。"""
    return _metrics
