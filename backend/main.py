"""
智能法律咨询助手 - FastAPI 后端服务（装配中心）

模块划分（按职责拆分，避免单一文件堆积）：
  - config.py          全局配置：路径、常量、容错设置
  - cache.py           问答语义缓存（LRU + TTL + 相似度命中）
  - resilience.py      容错：超时/重试/熔断/兜底
  - observability.py   可观测性：指标收集 + 结构化日志
  - data_input.py      文件解析、分块、检索展示
  - retrieval.py       混合检索：Jieba + 向量 + RRF 融合
  - kb_store.py        知识库存储：ChromaDB 用户隔离、文件导入、索引
  - llm_service.py     LLM 调用：非流式/流式 + 容错封装
  - prompt_builder.py  Prompt 构建

本文件职责：
  1. 应用/中间件初始化
  2. 嵌入函数创建与各模块装配（依赖注入）
  3. 路由依赖注入（startup 时）
"""
import os
import warnings
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from routes import router, init_routes
from database import init_user_table

from config import LAW_DIR, SAMPLE_DIR, ResilienceSettings
import chromadb.utils.embedding_functions as ef_utils

# 业务模块
import cache as cache_mod
import resilience as resilience_mod
import observability as observability_mod
import kb_store
import retrieval
import llm_service
import prompt_builder
from data_input import display_results

# 确保 backend 目录在搜索路径中
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 修复 Windows GBK 控制台打印中文/emoji 时报 UnicodeEncodeError 的问题
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
elif sys.platform == 'win32':
    try:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)
        sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)
    except Exception:
        pass

warnings.filterwarnings("ignore", category=UserWarning)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ============================================================
# 应用与中间件
# ============================================================
app = FastAPI(title="智能法律咨询助手", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 前端静态文件（单容器部署：FastAPI 直接 serve 前端构建产物）
# 前端构建目录 frontend/dist 存在时才挂载；本地开发用 vite dev server 时跳过。
# ============================================================
_FRONTEND_DIST = os.path.join(os.path.dirname(_BACKEND_DIR), "frontend", "dist")
if os.path.isdir(_FRONTEND_DIST):
    # 挂载静态资源（js/css 等）
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="assets")
    print(f"🌐 已挂载前端静态文件: {_FRONTEND_DIST}")

# ============================================================
# 全局单例（装配后供路由注入）
# ============================================================
_answer_cache = cache_mod.AnswerCache()
_resilience_settings = ResilienceSettings()
_circuit_breaker = resilience_mod.CircuitBreaker(
    _resilience_settings.circuit_threshold,
    _resilience_settings.circuit_cooldown,
)
_metrics_collector = observability_mod.get_metrics()

# ============================================================
# 嵌入函数（由 kb_store 持有，供语义缓存与向量检索使用）
# ============================================================
_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'


def _resolve_model_path():
    """优先使用本地已下载的模型（避免运行时从 HF 下载，容器内网络可能不通）。

    查找顺序：
      1. 环境变量 EMBED_MODEL_PATH 指定的路径
      2. 项目根 models/<model_name>（本地开发 + Docker 挂载目录，与 chroma_kb 分离）
    找到本地模型则返回本地路径，否则返回模型名（回退到 HF 下载）。
    """
    env_path = os.environ.get("EMBED_MODEL_PATH", "")
    if env_path and os.path.isdir(env_path):
        return env_path
    local = os.path.join(os.path.dirname(_BACKEND_DIR), "models", _MODEL_NAME)
    if os.path.isdir(local) and os.path.isfile(os.path.join(local, "config.json")):
        return local
    return _MODEL_NAME


class _AdaptiveBatchEmbeddingFunction(ef_utils.SentenceTransformerEmbeddingFunction):
    """按文本长度自适应分批的嵌入函数（继承官方实现，仅重写 __call__）。

    法律条文较短（每条几百字内），可加大 batch 提升 CPU 吞吐；
    案例是长文本（整篇一段，可达数千字），若按固定条数分批，单批 token
    总量会很大，导致内存峰值高、并行收益递减甚至更慢。

    因此这里按「累计字符总量」动态分组：短文本自然聚成较大的条数 batch，
    长文本则每批条数较少，从而在吞吐与内存之间取得平衡。

    继承官方 SentenceTransformerEmbeddingFunction 以复用其序列化
    （get_config / build_from_config / name）与协议校验能力。
    """

    # 实测结论（MiniLM 短条文，2 线程）：batch 越小越快，
    #   batch8=8.2s | batch16=8.9s | batch32=14.7s | batch128=17.3s（200条样本）。
    # 原因是短文本被 padding 到模型 max_seq_length，batch 越大 padding 浪费越多。
    # 因此短文本用小 batch=8，长文本（案例）用更小的 batch=4 控制内存。
    _LONG_TEXT_CHARS = 800      # 单条文本超过该字符数视为长文本（案例）
    _BATCH_LONG = 4             # 长文本 batch（条数，控制 padding 与内存）
    _BATCH_SHORT = 8            # 短文本 batch（条数，实测 8 最优）

    def __call__(self, input):
        import numpy as np
        docs = list(input)
        n = len(docs)
        if n == 0:
            return []

        # 记录原始索引，按长短分组 encode 后再按索引重排，保证输出顺序与输入一致
        result = [None] * n
        long_items = [(i, d) for i, d in enumerate(docs) if len(d) > self._LONG_TEXT_CHARS]
        short_items = [(i, d) for i, d in enumerate(docs) if len(d) <= self._LONG_TEXT_CHARS]

        for items, bs in ((long_items, self._BATCH_LONG),
                          (short_items, self._BATCH_SHORT)):
            for start in range(0, len(items), bs):
                chunk = items[start:start + bs]
                texts = [d for _, d in chunk]
                vecs = self._model.encode(
                    texts,
                    batch_size=bs,
                    convert_to_numpy=True,
                    normalize_embeddings=self.normalize_embeddings,
                )
                for (idx, _), v in zip(chunk, vecs):
                    result[idx] = np.array(v, dtype=np.float32)

        return result


def _configure_torch_threads():
    """设置 torch 线程数，加速 CPU 上的 embedding 推理。

    实测结论（MiniLM 小模型 + 短条文，200 条样本）：
      1 线程 18.6s | 2 线程 10.8s | 4 线程 15.9s | 8 线程 27.8s
    可见 2 线程最优，线程越多反而因调度/缓存竞争急剧变慢。
    因此固定为 2 线程，不受容器核数影响。
    """
    import torch
    torch.set_num_threads(2)
    print(f"⚙️ torch 线程数已设为 2（MiniLM 小模型实测最优，可用 CPU {os.cpu_count()} 核）")


def _create_embed_fn():
    model_ref = _resolve_model_path()
    if model_ref != _MODEL_NAME:
        print(f"🧠 使用本地嵌入模型: {model_ref}")
    return _AdaptiveBatchEmbeddingFunction(model_name=model_ref)


def _init_components():
    """装配各模块：注入嵌入函数、容错设置、熔断器。"""
    _configure_torch_threads()
    embed_fn = _create_embed_fn()

    # kb_store：注入嵌入函数
    kb_store.configure(embed_fn)

    # cache：注入向量化函数（用于问题语义相似度匹配）
    _answer_cache.embed_fn = embed_fn

    # llm_service：注入容错设置与熔断器
    llm_service.configure(_resilience_settings, _circuit_breaker)


# ============================================================
# 路由依赖注入 + 启动
# ============================================================

@app.on_event("startup")
def startup():
    init_user_table()  # 初始化用户数据库

    # 装配各业务模块（嵌入函数、容错、熔断）
    _init_components()

    # 初始化 ChromaDB 目录与旧数据清理
    kb_store.init_chroma()

    # 将核心依赖注入路由模块
    init_routes({
        "collection": None,             # 由 kb_store.get_active_state 提供实时状态
        "chunks": retrieval.chunks,
        "jieba_tokens": retrieval.jieba_tokens,
        "LAW_DIR": LAW_DIR,
        "SAMPLE_DIR": SAMPLE_DIR,
        "ensure_user_loaded": kb_store.ensure_user_loaded,
        "reset_all_kb": kb_store.reset_all_kb,
        "delete_user_data": kb_store.delete_user_data,
        "get_active_state": kb_store.get_active_state,
        "hybrid_search": retrieval.hybrid_search,
        "ask_llm": llm_service.ask_llm,
        "stream_llm": llm_service.stream_llm,
        "import_folder": kb_store.import_folder,
        "import_file": kb_store.import_file,
        "import_files": kb_store.import_files,
        "has_imported_file": kb_store.has_imported_file,
        "import_user_paths": kb_store.import_user_paths,
        "list_user_kb_files": kb_store.list_user_kb_files,
        "build_legal_prompt": prompt_builder.build_legal_prompt,
        "format_for_llm": prompt_builder.format_for_llm,
        "display_results": display_results,
        # 缓存 + 容错 + 监控依赖
        "answer_cache": _answer_cache,
        "circuit_breaker": _circuit_breaker,
        "metrics": _metrics_collector,
        "build_fallback_answer": resilience_mod.build_fallback_answer,
        "circuit_stats": lambda: _circuit_breaker.stats(),
        "resilience_stats": lambda: {
            "request_timeout": _resilience_settings.request_timeout,
            "max_retries": _resilience_settings.max_retries,
            "retry_base_delay": _resilience_settings.retry_base_delay,
            "circuit": _circuit_breaker.stats(),
        },
    })
    app.include_router(router)

    # SPA 回退：必须在所有 API 路由注册之后添加，否则会拦截 /api/* 请求
    if os.path.isdir(_FRONTEND_DIST):
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            candidate = os.path.join(_FRONTEND_DIST, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
