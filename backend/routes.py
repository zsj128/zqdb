"""
API 路由定义
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# --------------------- 请求模型 ---------------------

class SearchReq(BaseModel):
    query: str
    n_results: int = 5

class ChatReq(BaseModel):
    question: str
    n_results: int = 5
    api_key: str = ""
    model: str = ""
    base_url: str = ""

class RebuildReq(BaseModel):
    pdf_path: str
    source_type: str = "law"


# --------------------- 路由处理函数 ---------------------

# 下面的函数通过 init_routes() 注入依赖，避免循环引用
_deps = None

def init_routes(deps: dict):
    """注入全局依赖（由 main.py 启动时调用）"""
    global _deps
    _deps = deps


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
    imported = d["get_imported"]()
    result = {"law": [], "sample": []}
    for directory, key in [(d["LAW_DIR"], "law"), (d["SAMPLE_DIR"], "sample")]:
        import os
        if not os.path.isdir(directory):
            continue
        for f in sorted(os.listdir(directory)):
            if f.lower().endswith(('.pdf', '.docx')):
                result[key].append({
                    "filename": f,
                    "full_path": os.path.join(directory, f),
                    "imported": f in imported,
                })
    return result


@router.post("/api/search")
def search(req: SearchReq):
    d = _deps
    if not d["bm25_index"] or not d["collection"]:
        raise HTTPException(status_code=503, detail="知识库尚未初始化")
    results = d["hybrid_search"](req.query, req.n_results)
    return {"query": req.query, "count": len(results), "results": results}


@router.post("/api/chat")
def chat(req: ChatReq):
    """核心接口：RAG检索 → 格式化 → CoT Prompt → LLM生成"""
    d = _deps
    if not d["bm25_index"] or not d["collection"]:
        raise HTTPException(status_code=503, detail="知识库尚未初始化")

    # 法律至少取15条确保关键法条不被截断，案例另取2条
    law_candidates = d["hybrid_search"](req.question, max(req.n_results, 15), source_type="law")
    sample_candidates = d["hybrid_search"](req.question, 2, source_type="sample") if d["collection"].count() > 0 else []
    candidates = law_candidates + sample_candidates

    context_formatted = d["format_for_llm"](candidates)
    d["display_results"]([
        {"text": c["text"], "similarity": c.get("rrf_score", 0),
         "articles": c.get("articles", ""), "page": c.get("page")}
        for c in candidates
    ], title=f"📋 问答检索 [{req.question}]")

    prompt = d["build_legal_prompt"](req.question, context_formatted)
    answer = d["ask_llm"](prompt, api_key=req.api_key, base_url=req.base_url, model=req.model)

    return {
        "question": req.question,
        "answer": answer,
        "sources": [{
            "articles": c.get("articles", ""), "page": c.get("page", "?"),
            "score": c.get("rrf_score", 0), "text": c["text"],
            "source_file": c.get("source_file", ""),
        } for c in candidates],
    }


@router.post("/api/rebuild")
def rebuild(req: RebuildReq):
    import os
    from rank_bm25 import BM25Okapi
    import jieba

    d = _deps
    if not os.path.exists(req.pdf_path):
        raise HTTPException(status_code=404, detail=f"PDF不存在: {req.pdf_path}")
    try:
        new_count = d["import_one"](req.pdf_path, req.source_type)
        all_data = d["collection"].get(include=['documents', 'metadatas'])
        d["chunks"][:] = [
            {"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
            for i in range(len(all_data['ids']))
        ]
        d["bm25_index"] = BM25Okapi([list(jieba.cut(c["text"])) for c in d["chunks"]])
        return {
            "message": f"导入完成 (type={req.source_type})",
            "pdf": req.pdf_path,
            "chunks_parsed": new_count,
            "total_chunks": d["collection"].count(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
