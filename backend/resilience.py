# -*- coding: utf-8 -*-
"""
服务容错模块（参考 day63_resilience.py）

容错四件套：
  1. 超时 (with_timeout)  —— 不让请求无限等待
  2. 重试 (with_retry)    —— 瞬时故障指数退避重试（如 429 限流）
  3. 熔断 (CircuitBreaker) —— 连续失败达阈值就开路，冷却后半开试探
  4. 兜底 (fallback)      —— LLM 不可用时基于检索片段拼出可用的降级回答

对外主要接口：
  - call_with_resilience(coro_factory, breaker, settings, what)
      对任意可重复调用的协程工厂套上 超时+重试+熔断，成功复位、失败累计
  - CircuitBreaker(threshold, cooldown)
  - build_fallback_answer(...)  纯函数，生成降级回答文本
"""
import time
import asyncio


class CircuitOpenError(RuntimeError):
    """熔断器处于 OPEN 状态时抛出，外层不再尝试真实调用。"""


class CircuitBreaker:
    """CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN 状态机。"""

    def __init__(self, threshold: int = 3, cooldown: float = 10.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._opened_at = 0.0
        self.state = "CLOSED"

    def allow(self) -> bool:
        if self.state == "OPEN":
            if time.time() - self._opened_at >= self.cooldown:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def on_success(self):
        self._failures = 0
        self.state = "CLOSED"

    def on_failure(self):
        self._failures += 1
        if self._failures >= self.threshold:
            self.state = "OPEN"
            self._opened_at = time.time()

    def stats(self) -> dict:
        return {
            "state": self.state,
            "consecutive_failures": self._failures,
            "threshold": self.threshold,
        }


async def with_timeout(coro, timeout: float, what: str):
    """给任意协程套上限，超时抛 TimeoutError。"""
    return await asyncio.wait_for(coro, timeout=timeout)


async def with_retry(coro_factory, max_retries: int, base_delay: float, what: str):
    """瞬时故障重试 + 指数退避；coro_factory 是可重复调用的工厂。"""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (2 ** attempt))
    raise last_exc


async def call_with_resilience(coro_factory, breaker: CircuitBreaker,
                               settings, what: str):
    """熔断开路则直接抛 CircuitOpenError；否则尝试调用并更新熔断状态。"""
    if not breaker.allow():
        raise CircuitOpenError(f"{what} 熔断中（OPEN），直接走兜底")
    try:
        result = await with_timeout(
            with_retry(coro_factory, settings.max_retries, settings.retry_base_delay, what),
            settings.request_timeout, what,
        )
        breaker.on_success()
        return result
    except CircuitOpenError:
        raise
    except Exception:
        breaker.on_failure()
        raise


def build_fallback_answer(context: str, question: str, reason: str = "") -> str:
    """兜底件：LLM 不可用时，基于已检索到的法条拼一个可用的降级回答。

    - 有检索上下文：把法条原文作为"系统降级回复"返回，用户仍能拿到资料
    - 无检索上下文：返回明确的系统繁忙提示
    返回 (answer_text, degrade_reason)
    """
    if context and context.strip():
        ans = (
            "【系统降级回复】\n"
            "抱歉，智能模型当前暂时无法生成完整分析。以下是从法律知识库检索到的相关法条，"
            "您可以先参考；请稍后重试或补充更多描述以获得完整解答。\n\n"
            + context
        )
    else:
        ans = "系统暂时繁忙，无法生成回答。请稍后重试。"
    return ans, (reason or "LLM 调用失败")
