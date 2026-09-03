# -*- coding: utf-8 -*-
"""
LLM 调用服务模块：从 main.py 拆出。

包含：
  - asyncio_call_llm / await_result   同步调用 + 同步版 重试/熔断 容错（参考 day63）
  - ask_llm                           非流式问答（含历史记忆 + 容错）
  - stream_llm                        流式问答（含历史记忆 + 容错）

依赖注入：通过 configure() 传入容错设置、熔断器、聊天记忆等共享状态，
避免模块间直接 import main 造成循环依赖。
"""
import time as _time
import openai
from config import DEFAULT_BASE_URL
from resilience import CircuitOpenError
from observability import log_event


# ============================================================
# 模块级共享状态（由 main.configure_llm_service 注入）
# ============================================================
_settings = None      # ResilienceSettings
_breaker = None       # CircuitBreaker
_chat_memory = {}     # user_id -> {sid: [(q, a), ...]}
_next_sid = 1


def configure(resilience_settings, circuit_breaker):
    """注入容错设置与熔断器（在 app startup 时调用）。"""
    global _settings, _breaker
    _settings = resilience_settings
    _breaker = circuit_breaker


def _friendly_error(e):
    """把底层异常转成对用户友好、且不泄露敏感信息（如 API Key）的提示文案。

    针对 OpenAI 兼容接口的常见错误分类：
      - 认证失败（401）→ 提示 Key 无效/过期，绝不回显 Key 内容
      - 限流（429）→ 提示请求过于频繁
      - 参数/资源错误 → 简明提示
      - 其它 → 通用提示，仅记录原始错误到日志
    """
    # 401 认证类：AuthenticationError / PermissionDeniedError（不泄露 Key）
    if isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "API Key 无效或已过期，请在「知识库管理」中检查并重新配置 API Key。"
    # 429 限流
    if isinstance(e, openai.RateLimitError):
        return "请求过于频繁或额度不足，请稍后重试或检查账户配额。"
    # 400 参数错误
    if isinstance(e, openai.BadRequestError):
        msg = "请求参数有误，请检查模型名称或 Base URL 配置是否正确。"
        try:
            detail = getattr(e, "message", "") or ""
            if detail and "model" in detail.lower():
                msg = "模型不存在或不可用，请在「知识库管理」中检查模型名称配置。"
        except Exception:
            pass
        return msg
    # 其它：通用提示，不暴露原始 detail
    return "大模型服务调用异常，请稍后重试；若持续失败请检查网络或 LLM 配置。"


# ============================================================
# 同步调用 + 容错
# ============================================================

def asyncio_call_llm(prompt, messages, api_key, base_url, model):
    """同步包装：构造 OpenAI 客户端并调用（供容错层重试工厂使用）。"""
    client = openai.OpenAI(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL,
                           timeout=_settings.request_timeout)
    resp = client.chat.completions.create(
        model=model, messages=messages,
        max_tokens=4096, temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def await_result(settings, factory, breaker):
    """同步版 重试+熔断：对同步 LLM 调用容错（参考 day63 思想）。

    说明：本项目的非流式 ask_llm 是同步调用（返回 str），
    因此不能套用面向 async 的 call_with_resilience（它会 await 返回值导致报错）。
    这里实现同步版：超时由 openai 客户端 timeout 控制，重试用指数退避，失败计入熔断。
    """
    if not breaker.allow():
        raise CircuitOpenError("LLM 熔断中（OPEN），直接走兜底")
    last_exc = None
    for attempt in range(settings.max_retries + 1):
        try:
            result = factory()
            breaker.on_success()
            return result
        except Exception as e:
            last_exc = e
            if attempt < settings.max_retries:
                _time.sleep(settings.retry_base_delay * (2 ** attempt))
    breaker.on_failure()
    raise last_exc


# ============================================================
# 非流式问答
# ============================================================

def ask_llm(prompt, api_key="", base_url="", model="", sid="", user_id=0):
    """非流式问答，加入 超时+重试+熔断 容错（参考 day63）。

    返回 (answer, sid)。
    - 成功：正常答案
    - 失败且无检索上下文兜底：返回降级提示（不裸抛 500）
    """
    global _next_sid
    if not api_key:
        log_event("WARNING", "llm_no_key", user_id=user_id)
        return "⚠ 尚未配置 API Key，请先在「知识库管理」中保存 LLM 配置。", sid or ""

    # 构造该用户的历史消息
    mem = _chat_memory.setdefault(user_id, {})
    messages = []
    if sid and sid in mem:
        for q, a in mem[sid]:
            messages.append({"role": "user", "content": q})
            messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": prompt})

    if not sid:
        sid = str(_next_sid)
        _next_sid += 1

    def factory():
        return asyncio_call_llm(prompt, messages, api_key, base_url, model)

    try:
        answer = await_result(_settings, factory, _breaker)
    except CircuitOpenError:
        log_event("WARNING", "llm_circuit_open", user_id=user_id,
                  circuit=_breaker.state)
        return "⚠ 模型服务暂时不可用（已熔断保护），请稍后重试。", sid
    except Exception as e:
        log_event("ERROR", "llm_failed", user_id=user_id, err=str(e)[:120])
        return f"⚠ {_friendly_error(e)}", sid

    mem.setdefault(sid, []).append((prompt, answer))
    return answer, sid


# ============================================================
# 流式问答
# ============================================================

def stream_llm(prompt, api_key="", base_url="", model="", sid="", user_id=0):
    """流式调用 LLM，逐块 yield (delta_text)。

    返回 (generator, session_id)：
    - generator 逐块产出增量文本
    - session_id 为最终会话ID（用于对话记忆存储）
    完整回答结束后由调用方负责写入 _chat_memory[user_id]。

    容错（参考 day63）：流式建立连接时套 超时+重试+熔断，
    上游(LLM)不稳定时首块给出降级提示，不给用户裸报错。
    """
    global _next_sid
    if not api_key:
        log_event("WARNING", "llm_no_key", user_id=user_id)
        return (x for x in ["⚠ 尚未配置 API Key，请先在「知识库管理」中保存 LLM 配置。"]), sid or ""

    try:
        mem = _chat_memory.setdefault(user_id, {})
        # 前置对话（历史记忆）
        messages = []
        if sid and sid in mem:
            for q, a in mem[sid]:
                messages.append({"role": "user", "content": q})
                messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": prompt})

        # 没带 sid 就分配一个数字
        final_sid = sid
        if not final_sid:
            final_sid = str(_next_sid)
            _next_sid += 1

        def _open_stream():
            """可重试的流式连接工厂：返回已建立的 stream 迭代器。

            注意：openai 同步客户端的 stream=True 返回 Stream 对象（可迭代、非协程），
            因此这里直接用同步重试+熔断，而非 call_with_resilience（后者面向 async）。
            """
            client = openai.OpenAI(
                api_key=api_key, base_url=base_url or DEFAULT_BASE_URL,
                timeout=_settings.request_timeout,
            )
            return client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=4096, temperature=0.3, stream=True,
            )

        def _open_with_resilience():
            """同步版 重试+熔断：对建立流式连接容错。"""
            if not _breaker.allow():
                raise CircuitOpenError("LLM 熔断中（OPEN），直接走兜底")
            last_exc = None
            for attempt in range(_settings.max_retries + 1):
                try:
                    s = _open_stream()
                    _breaker.on_success()
                    return s
                except Exception as e:
                    last_exc = e
                    if attempt < _settings.max_retries:
                        _time.sleep(_settings.retry_base_delay * (2 ** attempt))
            _breaker.on_failure()
            raise last_exc

        def gen():
            full = ""
            try:
                # 对"建立连接"套同步容错（重试+熔断），超时由客户端 timeout 控制
                stream = _open_with_resilience()
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full += delta
                        yield delta
            except CircuitOpenError:
                msg = "⚠ 模型服务暂时不可用（已熔断保护），请稍后重试。"
                log_event("WARNING", "llm_circuit_open", user_id=user_id,
                          circuit=_breaker.state)
                yield msg if not full else f"\n{msg}"
            except Exception as e:
                msg = f"⚠ {_friendly_error(e)}"
                log_event("ERROR", "llm_failed", user_id=user_id, err=str(e)[:120])
                # 若此前已输出过内容，追加错误说明
                yield msg if not full else f"\n{msg}"
                if full:
                    mem.setdefault(final_sid, []).append((prompt, full))
                    return
                mem.setdefault(final_sid, []).append((prompt, msg))
                return
            # 正常结束，写入对话记忆
            mem.setdefault(final_sid, []).append((prompt, full))

        return gen(), final_sid
    except Exception as e:
        # 客户端初始化失败等外层错误
        log_event("ERROR", "llm_stream_setup_failed", err=str(e)[:120])
        return (x for x in [f"⚠ {_friendly_error(e)}"]), sid or ""
