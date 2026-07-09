"""
API 路由定义
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class SearchReq(BaseModel):
    query: str
    n_results: int = 5

class ChatReq(BaseModel):
    question: str
    n_results: int = 5
    api_key: str = ""
    model: str = ""
    base_url: str = ""

# 登录注册请求模型
class RegisterReq(BaseModel):
    username: str
    password: str
    email: str = ""
    phone: str = ""

class LoginReq(BaseModel):
    username: str
    password: str

_deps = None

def init_routes(deps: dict):
    """注入全局依赖（由 main.py 启动时调用）"""
    global _deps
    _deps = deps


@router.post("/api/register")
def register(req: RegisterReq):
    """用户注册接口"""
    #接收前端注册请求 → 调用数据库层写入 → 成功返回结果 / 失败返回 400 错误。
    from database import register_user
    result = register_user(req.username, req.password, req.email, req.phone)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/api/login")
def login(req: LoginReq):
    """用户登录接口"""
    from database import login_user
    result = login_user(req.username, req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    # 返回简单token
    result["token"] = f"token_{result['user_id']}_{req.username}"
    # 登录成功 → 后端返回 {token: "token_1_zhangsan"}
    return result


@router.get("/")
def root():
    return {
        "service": "智能法律咨询助手", "version": "1.0.0",
        "endpoints": {
            "/api/search": "POST-法条检索",
            "/api/chat": "POST-AI问答",
            "/api/rebuild": "POST-导入知识库",
            "/api/stats": "GET-统计",
        },
    }


@router.get("/api/stats")
def get_stats():
    d = _deps
    law_n, sample_n = 0, 0
    if d["chunks"]:
        for c in d["chunks"]:
            st = c.get('source_type', '')
            if st == 'law':
                law_n += 1
            elif st == 'sample':
                sample_n += 1
    return {
        "total_chunks": d["collection"].count() if d["collection"] else 0,
        "law_chunks": law_n,
        "sample_chunks": sample_n,
    }


@router.get("/api/files")
def list_files():
    d = _deps
    result = {"law": [], "sample": []}
    for directory, key in [(d["LAW_DIR"], "law"), (d["SAMPLE_DIR"], "sample")]:
        import os
        if not os.path.isdir(directory):
            continue
        for f in sorted(os.listdir(directory)):
            if f.lower().endswith(('.pdf', '.docx')):
                result[key].append({
                    "filename": f,
                })
    return result


@router.post("/api/search")
def search(req: SearchReq):
    d = _deps
    if not d["jieba_tokens"] or not d["collection"]:
        raise HTTPException(status_code=503, detail="知识库尚未初始化")
    results = d["hybrid_search"](req.query, req.n_results)
    return {"query": req.query, "count": len(results), "results": results}


@router.post("/api/chat")
def chat(req: ChatReq):
    """核心接口：RAG检索 → 格式化 → CoT Prompt → LLM生成"""
    d = _deps
    if not d["jieba_tokens"] or not d["collection"]:
        raise HTTPException(status_code=503, detail="知识库尚未初始化")

    # 法律至少取15条确保关键法条不被截断，案例另取2条
    law_candidates = d["hybrid_search"](req.question, max(req.n_results, 15), source_type="law")
    sample_candidates = d["hybrid_search"](req.question, 2, source_type="sample") if d["collection"].count() > 0 else []
    candidates = law_candidates + sample_candidates

    context_formatted = d["format_for_llm"](candidates)
    d["display_results"]([
        {"text": c["text"], "similarity": c.get("rrf_score", 0),
         "articles": c.get("articles", "")}
        for c in candidates
    ], title=f"📋 问答检索 [{req.question}]")

    prompt = d["build_legal_prompt"](req.question, context_formatted)
    answer = d["ask_llm"](prompt, api_key=req.api_key, base_url=req.base_url, model=req.model)

    return {
        "question": req.question,
        "answer": answer,
        "sources": [{
            "articles": c.get("articles", ""), 
            "score": c.get("rrf_score", 0), "text": c["text"],
            "source_file": c.get("source_file", ""),
            "source_type": c.get("source_type", ""),
            "article_content": c.get("article_content", ""),
            "article_key": c.get("article_key", ""),
        } for c in candidates],
    }



