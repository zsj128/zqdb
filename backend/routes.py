"""
API 路由定义
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import json
import tempfile
from database import register_user
from database import login_user
from database import save_user_import, get_user_imports
from database import get_user_llm_config, save_user_llm_config
from database import is_admin_user, list_all_tables, delete_user_all_data, delete_table_row
from data_input import parse_attachment
from observability import log_event, get_metrics
from config import DATA_DIR

router = APIRouter()

# 允许的附件格式（问答中上传，作为单次对话上下文）
ALLOWED_ATTACHMENT_EXTS = ('.pdf', '.docx', '.doc', '.md', '.txt')
MAX_ATTACHMENT_CHARS = 8000


def _parse_uploaded_attachment(file: UploadFile):
    """解析上传的附件为纯文本（用于对话上下文），失败时抛 HTTPException。"""
    if file is None or not file.filename:
        return "", ""
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTS:
        raise HTTPException(status_code=400,
                            detail=f"不支持的附件格式: {ext}，仅支持 {', '.join(ALLOWED_ATTACHMENT_EXTS)}")
    # 写入临时文件再解析（parse_attachment 依赖文件路径）
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            content = file.file.read()
            tmp.write(content)
            tmp_path = tmp.name
        text = parse_attachment(tmp_path, max_chars=MAX_ATTACHMENT_CHARS)
        return filename, text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"附件解析失败: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

class SearchReq(BaseModel):
    query: str
    n_results: int = 5
    user_id: int = 0

class ChatReq(BaseModel):
    question: str
    n_results: int = 5
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    session_id: str = ""   
    user_id: int = 0

class FolderImportReq(BaseModel):
    path: str                  # 服务器上的目录地址
    source_type: str = "law"   # law=法律文件 | sample=法律案例
    user_id: int = 0

class LlmConfigReq(BaseModel):
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    user_id: int = 0

# 登录注册请求模型
class RegisterReq(BaseModel):
    username: str
    password: str
    email: str = ""
    phone: str = ""

class LoginReq(BaseModel):
    username: str
    password: str

class AdminDeleteReq(BaseModel):
    username: str = ""     # 管理员当前登录用户名（用于鉴权）
    identifier: str        # 要删除的目标：用户名 或 用户ID

class AdminViewReq(BaseModel):
    username: str = ""     # 管理员当前登录用户名（用于鉴权）

class AdminDeleteRowReq(BaseModel):
    username: str = ""     # 管理员当前登录用户名（用于鉴权）
    table: str             # 表名（users / user_imports / user_llm_config）
    pk_value: str          # 该表主键值（user_llm_config 为 user_id）

_deps = None


def _resolve_llm_config(user_id, api_key="", model="", base_url=""):
    """解析某用户的 LLM 配置：优先用请求传入的值；未传则用该用户绑定的配置。"""
    cfg = get_user_llm_config(user_id)
    return {
        "api_key": api_key if api_key else cfg.get("api_key", ""),
        "model": model if model else cfg.get("model", ""),
        "base_url": base_url if base_url else cfg.get("base_url", ""),
    }


def init_routes(deps: dict):
    """注入全局依赖（由 main.py 启动时调用）"""
    global _deps
    _deps = deps


@router.post("/api/register")
def register(req: RegisterReq):
    """用户注册接口"""
    #接收前端注册请求 → 调用数据库层写入 → 成功返回结果 / 失败返回 400 错误。
    result = register_user(req.username, req.password, req.email, req.phone)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/api/login")
def login(req: LoginReq):
    """用户登录接口"""
    result = login_user(req.username, req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    # 返回简单token
    result["token"] = f"token_{result['user_id']}_{req.username}"
    # 登录成功 → 后端返回 {token: "token_1_zhangsan", is_admin: bool}
    return result


# ============================================================
# 管理员接口
# ============================================================

def _require_admin(username: str):
    """管理员鉴权：非 admin 直接拒绝。"""
    if not is_admin_user(username):
        raise HTTPException(status_code=403, detail="无管理员权限")


@router.post("/api/admin/tables")
def admin_view_tables(req: AdminViewReq):
    """管理员：查看 MySQL 数据库中所有表的所有数据。"""
    _require_admin(req.username)
    result = list_all_tables()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "查询失败"))
    return result


@router.post("/api/admin/delete_user")
def admin_delete_user(req: AdminDeleteReq):
    """管理员：删除指定用户名或用户ID的账号及其所有 MySQL 数据。"""
    _require_admin(req.username)
    if not req.identifier:
        raise HTTPException(status_code=400, detail="请提供要删除的用户名或用户ID")
    result = delete_user_all_data(req.identifier)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "删除失败"))
    return result


@router.post("/api/admin/delete_row")
def admin_delete_row(req: AdminDeleteRowReq):
    """管理员：按主键删除指定表中的一行数据。

    - users / user_imports：按 id 删除
    - user_llm_config：按 user_id 删除
    """
    _require_admin(req.username)
    if not req.table or not req.pk_value:
        raise HTTPException(status_code=400, detail="缺少表名或主键值")
    result = delete_table_row(req.table, req.pk_value)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "删除失败"))
    return result


@router.get("/api/files")
def list_files():
    d = _deps
    result = {"law": [], "sample": []}
    for directory, key in [(d["LAW_DIR"], "law"), (d["SAMPLE_DIR"], "sample")]:
        if not os.path.isdir(directory):
            continue
        for f in sorted(os.listdir(directory)):
            if f.lower().endswith(('.pdf', '.docx')):
                result[key].append({
                    "filename": f,
                })
    return result


@router.post("/api/kb/files")
def kb_files(req: FolderImportReq):
    """返回当前用户知识库中实际已加载的文件列表（按 source_file 聚合）。

    用于让用户确认文件是否加载成功。
    """
    d = _deps
    if req.user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    return d["list_user_kb_files"](req.user_id)


@router.post("/api/kb/delete")
def delete_user_kb(req: FolderImportReq):
    """删除当前用户的本地数据（知识库向量目录 + 上传文件目录）。

    用于让用户一键清空自己的本地数据，像系统软件一样可自管理存储。
    """
    d = _deps
    if req.user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    try:
        result = d["delete_user_data"](req.user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    return {"success": True, "result": result}


# 单个文件上传的落盘目录（用户数据目录 ~/.law_ai/data/upload）
_UPLOAD_ROOT = os.path.join(DATA_DIR, 'upload')


@router.post("/api/import/folder")
def import_folder(req: FolderImportReq):
    """整目录导入：读取服务器上一个目录里的全部 .pdf/.docx，并记录该目录地址到用户。"""
    d = _deps
    if req.source_type not in ("law", "sample"):
        raise HTTPException(status_code=400, detail="source_type 仅支持 law / sample")
    if req.user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    # 绑定/加载该用户的知识库集合（内部会校验 ChromaDB 是否已初始化）
    d["ensure_user_loaded"](req.user_id)
    try:
        result = d["import_folder"](req.path, req.source_type)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    saved = False
    r = save_user_import(req.user_id, req.source_type, "folder", os.path.abspath(req.path))
    saved = r.get("saved", False)
    return {"success": True, "result": result, "saved": saved}


@router.post("/api/import/file")
async def import_file(
    file: UploadFile = File(...),
    source_type: str = Form("law"),
    user_id: int = Form(0),
):
    """单文件导入：上传一个 .pdf/.docx 文件，保存到服务器并导入知识库，记录该路径到用户。"""
    d = _deps
    if source_type not in ("law", "sample"):
        raise HTTPException(status_code=400, detail="source_type 仅支持 law / sample")
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    # 绑定/加载该用户的知识库集合（内部会校验 ChromaDB 是否已初始化）
    d["ensure_user_loaded"](user_id)

    filename = os.path.basename(file.filename or "")
    if not filename or not filename.lower().endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="仅支持 .pdf / .docx 文件")

    # 同名跳过：用「原始文件名」判断该用户知识库中是否已存在此文件。
    # 注意：必须在落盘改名（_1、_2 后缀）之前判断，否则改名后 source_file
    # 永远对不上，导致同名文件被重复导入。
    if d["has_imported_file"](user_id, filename):
        return {"success": True, "filename": filename,
                "result": {"count": 0, "skipped": 1, "errors": [], "files": 1, "already": True},
                "saved": False}

    # 落盘到 data/upload/<user_id>/<文件名>，避免重名加时间戳
    user_sub = str(user_id) if user_id > 0 else "guest"
    dest_dir = os.path.join(_UPLOAD_ROOT, user_sub)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1

    try:
        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
    finally:
        await file.close()

    try:
        result = d["import_file"](dest_path, source_type)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    saved = False
    if user_id > 0 and not result.get("already"):
        r = save_user_import(user_id, source_type, "file", dest_path)
        saved = r.get("saved", False)
    return {"success": True, "filename": os.path.basename(dest_path), "result": result, "saved": saved}


@router.post("/api/import/files")
async def import_files(
    files: list[UploadFile] = File(...),
    source_type: str = Form("law"),
    user_id: int = Form(0),
):
    """多文件批量导入：一次请求上传多个 .pdf/.docx，全部入库后仅重建一次索引。

    相比前端逐个调用 /api/import/file，这里把所有文件落盘后统一交给
    kb_store.import_files 处理，避免每个文件都全量重建 Jieba 索引。
    """
    d = _deps
    if source_type not in ("law", "sample"):
        raise HTTPException(status_code=400, detail="source_type 仅支持 law / sample")
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    if not files:
        raise HTTPException(status_code=400, detail="未收到任何文件")
    d["ensure_user_loaded"](user_id)

    # 落盘到 data/upload/<user_id>/，避免重名加时间戳
    user_sub = str(user_id)
    dest_dir = os.path.join(_UPLOAD_ROOT, user_sub)
    os.makedirs(dest_dir, exist_ok=True)

    saved_paths = []
    for file in files:
        filename = os.path.basename(file.filename or "")
        if not filename or not filename.lower().endswith(('.pdf', '.docx')):
            continue
        # 同名跳过：原始文件名已存在则不再落盘导入（避免改名 _1 后缀后重复入库）
        if d["has_imported_file"](user_id, filename):
            continue
        dest_path = os.path.join(dest_dir, filename)
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
            counter += 1
        try:
            content = await file.read()
            with open(dest_path, "wb") as f:
                f.write(content)
            saved_paths.append(dest_path)
        except Exception:
            continue
        finally:
            await file.close()

    if not saved_paths:
        raise HTTPException(status_code=400, detail="没有可导入的 .pdf / .docx 文件")

    try:
        result = d["import_files"](saved_paths, source_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    # 记录每个成功导入的文件路径到用户（跳过已存在 / 失败的）
    saved = False
    if result.get("count", 0) > 0:
        r = save_user_import(user_id, source_type, "folder",
                             os.path.join(dest_dir))
        saved = r.get("saved", False)
    return {"success": True, "result": result, "saved": saved}


@router.post("/api/import/reload")
def reload_imports(req: FolderImportReq):
    """登录后调用：根据该用户已保存的所有目录/文件路径，重新导入知识库。"""
    d = _deps
    if req.user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    # 绑定该用户知识库并导入其已保存路径
    info = d["ensure_user_loaded"](req.user_id)
    result = d["import_user_paths"](req.user_id, source_type=req.source_type)
    # 返回该用户所有已保存路径清单
    records = get_user_imports(req.user_id, source_type=req.source_type)
    return {"success": True, "result": result, "records": records, "kb_count": info.get("count", 0)}


@router.get("/api/llm/config")
def get_llm_config(user_id: int = 0):
    """读取某用户绑定的 LLM 配置"""
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    return get_user_llm_config(user_id)


@router.post("/api/llm/config")
def post_llm_config(req: LlmConfigReq):
    """保存某用户绑定的 LLM 配置"""
    if req.user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    result = save_user_llm_config(req.user_id, req.api_key, req.model, req.base_url)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/api/search")
def search(req: SearchReq):
    d = _deps
    if req.user_id > 0:
        d["ensure_user_loaded"](req.user_id)
    st = d["get_active_state"]()
    if not st["jieba_tokens"]:
        return {"query": req.query, "count": 0, "results": []}
    results = d["hybrid_search"](req.query, req.n_results)
    return {"query": req.query, "count": len(results), "results": results}


@router.post("/api/chat")
async def chat(
    question: str = Form(...),
    user_id: int = Form(0),
    n_results: int = Form(5),
    api_key: str = Form(""),
    model: str = Form(""),
    base_url: str = Form(""),
    session_id: str = Form(""),
    file: UploadFile | None = File(None),   # 可选附件（单次对话上下文，不入库）
):
    """核心接口：RAG检索 → 格式化 → CoT Prompt → LLM生成
    （支持记忆 + 附件上下文 + 问答缓存 + 容错兜底 + 监控埋点）

    降级链路（参考 day63）：
      1) 缓存命中 → 直接返回（不调模型）
      2) 正常调模型（套 超时+重试+熔断）
      3) 模型失败 → 基于已检索法条拼兜底回答，绝不裸报 500
    """
    import time
    d = _deps
    t0 = time.time()

    # 解析附件（若有）
    attachment_name, attachment_text = _parse_uploaded_attachment(file)
    if user_id > 0:
        d["ensure_user_loaded"](user_id)
    st = d["get_active_state"]()
    if not st["jieba_tokens"] and not attachment_text:
        return {"question": question, "answer": "知识库暂无数据，请先导入", "session_id": session_id, "sources": []}

    # RAG 检索：附件内容与用户输入一起参与检索（附件优先，保证问题在附件里也能命中法条）
    search_query = question
    if attachment_text:
        search_query = f"{question}\n{attachment_text}".strip()
    law_candidates = d["hybrid_search"](search_query, max(n_results, 15), source_type="law")
    sample_candidates = d["hybrid_search"](search_query, 2, source_type="sample") if st["count"] > 0 else []
    candidates = law_candidates + sample_candidates

    context_formatted = d["format_for_llm"](candidates)
    d["display_results"]([
        {"text": c["text"], "similarity": c.get("rrf_score", 0),
         "articles": c.get("articles", "")}
        for c in candidates
    ], title=f"📋 问答检索 [{question}]")

    # 解析该用户绑定的 LLM 配置
    cfg = _resolve_llm_config(user_id, api_key, model, base_url)
    model_name = cfg["model"] or "qwen-plus"

    # ===== 1. 缓存优先（key 含 问题+上下文+模型，法条更新后自动失效）=====
    cache = d.get("answer_cache")
    cached = cache.get(question, context_formatted, model_name) if cache else None
    if cached is not None:
        out_sid = session_id
        latency = round((time.time() - t0) * 1000, 1)
        d.get("metrics", get_metrics()).observe(latency_ms=latency, cache_hit=True, degraded=False)
        log_event("INFO", "chat_cache_hit", user_id=user_id, q=question[:20], latency_ms=latency)
        return {
            "question": question,
            "answer": cached,
            "session_id": out_sid,
            "attachment": attachment_name or "",
            "cache_hit": True,
            "sources": _format_sources(candidates),
        }

    # ===== 2. 构造 Prompt 并调用 LLM（容错在 ask_llm 内）=====
    prompt = d["build_legal_prompt"](question, context_formatted,
                                     attachment_text=attachment_text,
                                     attachment_name=attachment_name)
    answer, out_sid = d["ask_llm"](
        prompt,
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=model_name,
        sid=session_id,
        user_id=user_id,
    )

    # ===== 3. 兜底判断：模型失败（带 ⚠ 前缀）且知识库有内容 → 拼降级回答 =====
    degraded = answer.startswith("⚠") or "大模型调用失败" in answer
    degrade_reason = ""
    if degraded and candidates:
        fallback_text, degrade_reason = d["build_fallback_answer"](context_formatted, question,
                                                                   reason="LLM 调用失败")
        # 仍把原始错误作为降级提示附加在顶部，用户可感知
        answer = answer + "\n\n" + fallback_text
        log_event("WARNING", "chat_degraded", user_id=user_id, q=question[:20],
                  reason=degrade_reason)

    # ===== 4. 缓存未命中：写入缓存（仅缓存成功、非降级、无附件的回答）=====
    if cache and not degraded and not attachment_text:
        cache.set(question, context_formatted, model_name, answer)

    # ===== 5. 监控埋点 =====
    latency = round((time.time() - t0) * 1000, 1)
    d.get("metrics", get_metrics()).observe(latency_ms=latency, cache_hit=False,
                                            degraded=degraded, degrade_reason=degrade_reason)
    log_event("INFO", "chat", user_id=user_id, q=question[:20],
              latency_ms=latency, degraded=degraded)

    return {
        "question": question,
        "answer": answer,
        "session_id": out_sid,
        "attachment": attachment_name or "",
        "cache_hit": False,
        "degraded": degraded,
        "sources": _format_sources(candidates),
    }


def _format_sources(candidates):
    """把检索候选列表格式化为前端需要的 sources 结构。"""
    return [{
        "articles": c.get("articles", ""),
        "score": c.get("rrf_score", 0),
        "text": c["text"],
        "source_file": c.get("source_file", ""),
        "source_type": c.get("source_type", ""),
        "article_content": c.get("article_content", ""),
        "article_key": c.get("article_key", ""),
    } for c in candidates]


def _collect_sources(d, question, n_results):
    """构造 sources 数据（流式端点的元数据）"""
    st = d["get_active_state"]()
    law_candidates = d["hybrid_search"](question, max(n_results, 15), source_type="law")
    sample_candidates = d["hybrid_search"](question, 2, source_type="sample") if st["count"] > 0 else []
    candidates = law_candidates + sample_candidates
    return candidates, _format_sources(candidates)


@router.post("/api/chat/stream")
async def chat_stream(
    question: str = Form(...),
    user_id: int = Form(0),
    n_results: int = Form(5),
    api_key: str = Form(""),
    model: str = Form(""),
    base_url: str = Form(""),
    session_id: str = Form(""),
    file: UploadFile | None = File(None),   # 可选附件（单次对话上下文，不入库）
):
    """流式问答接口：RAG检索 → SSE 逐块流式输出（支持附件 + 缓存 + 监控）

    发送事件序列（event + JSON data）：
      1. event=META    data={"sources": [...], "session_id": "...", "cache_hit": bool}
      2. event=DELTA   data={"delta": "增量文本"}      （可多次）
      3. event=DONE    data={"session_id": "...", "answer": "完整回答", "cache_hit": bool}
    """
    import time
    d = _deps
    t0 = time.time()
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="缺少 user_id")
    d["ensure_user_loaded"](user_id)

    # 解析附件（若有）
    attachment_name, attachment_text = _parse_uploaded_attachment(file)

    def _sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    st = d["get_active_state"]()
    if not st["jieba_tokens"] and not attachment_text:
        # 无数据时也按流式格式返回提示
        def _empty_sse():
            yield _sse("META", {"sources": [], "session_id": session_id, "cache_hit": False})
            yield _sse("DELTA", {"delta": "知识库暂无数据，请先导入法律文件或案例。"})
            yield _sse("DONE", {"session_id": session_id, "answer": "知识库暂无数据，请先导入法律文件或案例。", "cache_hit": False})
        return StreamingResponse(_empty_sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

    cfg = _resolve_llm_config(user_id, api_key, model, base_url)
    model_name = cfg["model"] or "qwen-plus"
    cache = d.get("answer_cache")

    def _generator():
        # 1. RAG 检索 + 来源元数据（附件内容与用户输入一起参与检索）
        search_query = question
        if attachment_text:
            search_query = f"{question}\n{attachment_text}".strip()
        candidates, sources = _collect_sources(d, search_query, n_results)
        context_formatted = d["format_for_llm"](candidates)
        d["display_results"]([
            {"text": c["text"], "similarity": c.get("rrf_score", 0),
             "articles": c.get("articles", "")} for c in candidates
        ], title=f"📋 问答检索 [{question}]")

        # 1.5 缓存优先：命中直接整体返回（不流式）
        if cache and not attachment_text:
            cached = cache.get(question, context_formatted, model_name)
            if cached is not None:
                latency = round((time.time() - t0) * 1000, 1)
                d.get("metrics", get_metrics()).observe(latency_ms=latency,
                                                        cache_hit=True, degraded=False)
                log_event("INFO", "chat_stream_cache_hit", user_id=user_id,
                          q=question[:20], latency_ms=latency)
                yield _sse("META", {"sources": sources, "session_id": session_id,
                                    "attachment": attachment_name, "cache_hit": True})
                yield _sse("DELTA", {"delta": cached})
                yield _sse("DONE", {"session_id": session_id, "answer": cached, "cache_hit": True})
                return

        prompt = d["build_legal_prompt"](question, context_formatted,
                                         attachment_text=attachment_text,
                                         attachment_name=attachment_name)

        # 2. 先发 META（来源 + 会话ID + 附件名 + cache_hit=False）
        temp_sid = session_id
        yield _sse("META", {"sources": sources, "session_id": temp_sid,
                            "attachment": attachment_name, "cache_hit": False})

        # 3. 流式生成 LLM 应答（使用该用户绑定的 LLM 配置）
        stream_gen, final_sid = d["stream_llm"](
            prompt, api_key=cfg["api_key"], base_url=cfg["base_url"],
            model=model_name, sid=session_id, user_id=user_id,
        )

        full_answer = ""
        degraded = False
        try:
            for chunk in stream_gen:
                if not chunk:
                    continue
                full_answer += chunk
                if not degraded and ("⚠" in chunk or "调用失败" in chunk):
                    degraded = True
                yield _sse("DELTA", {"delta": chunk})
        except Exception as e:
            err = f"⚠ 流式生成异常: {e}"
            full_answer += err
            degraded = True
            yield _sse("DELTA", {"delta": err})

        # 3.5 缓存未命中且成功：写入缓存（非降级、无附件）
        if cache and not degraded and not attachment_text:
            cache.set(question, context_formatted, model_name, full_answer)

        # 4. 监控埋点 + 结束事件
        latency = round((time.time() - t0) * 1000, 1)
        d.get("metrics", get_metrics()).observe(latency_ms=latency, cache_hit=False,
                                                degraded=degraded)
        log_event("INFO", "chat_stream", user_id=user_id, q=question[:20],
                  latency_ms=latency, degraded=degraded)
        yield _sse("DONE", {"session_id": final_sid, "answer": full_answer, "cache_hit": False})

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/metrics")
def metrics_endpoint():
    """系统监控指标（参考 day64）：请求数 / 缓存命中率 / 降级率 / 延迟分位数。

    供前端「知识库管理」页的监控面板展示，也可被 Prometheus 风格拉取。
    """
    d = _deps
    snap = d.get("metrics", get_metrics()).snapshot()
    return {
        "metrics": snap,
        "circuit": d.get("circuit_stats", lambda: {})() if d else {},
    }


@router.get("/api/resilience")
def resilience_endpoint():
    """查看当前容错状态：熔断状态、超时/重试参数。便于排障。"""
    d = _deps
    if not d:
        return {}
    return d.get("resilience_stats", lambda: {})()
