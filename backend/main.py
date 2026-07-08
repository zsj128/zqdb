"""
智能法律咨询助手 - FastAPI 后端服务

核心流程:
  PDF → dpf_input.chunk_pdf分块 → ChromaDB入库
  用户问题 → search_chunks向量检索 + BM25关键词 → RRF融合排序 → CoT Prompt → 千问生成答案
"""
import os, warnings
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 确保 backend 目录在搜索路径中
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in os.sys.path:
    os.sys.path.insert(0, _BACKEND_DIR)

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(_BACKEND_DIR), '.env'))

from data_input import chunk_document, search_chunks, display_results

warnings.filterwarnings("ignore", category=UserWarning)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ============================================================
# 配置（LLM 参数由前端动态传入）
# ============================================================
CHROMA_PATH = os.path.join(os.path.dirname(_BACKEND_DIR), 'chroma_kb')
DATA_DIR = os.path.join(os.path.dirname(_BACKEND_DIR), 'data')
LAW_DIR = os.path.join(DATA_DIR, 'law')
SAMPLE_DIR = os.path.join(DATA_DIR, 'sample')

app = FastAPI(title="智能法律咨询助手", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 全局资源
collection = None
chunks = []
bm25_index = None

# 默认 LLM 配置（可通过 .env 覆盖）
_DEFAULT_API_KEY = os.getenv("QWEN_APP_KEY", "")
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-plus"


def _make_client(api_key: str = "", base_url: str = ""):
    """创建 OpenAI 兼容客户端"""
    return openai.OpenAI(
        api_key=api_key or _DEFAULT_API_KEY,
        base_url=base_url or _DEFAULT_BASE_URL,
    )


# ============================================================
# ChromaDB 初始化 + 自动导入
# ============================================================

def init_chroma():
    """初始化 ChromaDB → 扫描 law/sample 目录自动导入 → 构建索引"""
    global collection, chunks, bm25_index
    import chromadb
    import chromadb.utils.embedding_functions as ef_utils

    embedding_fn = ef_utils.SentenceTransformerEmbeddingFunction(
        model_name='paraphrase-multilingual-MiniLM-L12-v2'
    )
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name='pdf_knowledge_base_v3',
        metadata={"description": "法律知识库", "hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    # 加载已有数据并构建 BM25 索引
    if collection.count() > 0:
        all_data = collection.get(include=['documents', 'metadatas'])
        chunks = [{"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
                  for i in range(len(all_data['ids']))]
        bm25_index = BM25Okapi([list(jieba.cut(c["text"])) for c in chunks])
        print(f"ChromaDB 已加载: {collection.count()} 条数据, BM25 索引已构建")

    # 自动扫描并导入新文件
    _auto_import()


def _get_imported():
    if not collection or collection.count() == 0:
        return set()
    return {m.get('source_file', '') for m in collection.get(include=['metadatas'])['metadatas'] if m.get('source_file')}


def _import_one(pdf_path, source_type):
    """解析单个PDF并入库"""
    filename = os.path.basename(pdf_path)
    print(f"  📄 解析 [{source_type}] {filename} ...")
    raw = chunk_document(pdf_path, source_type=source_type)
    total = 0
    for start in range(0, len(raw), 500):
        batch = raw[start:start + 500]
        docs = [c['text'] for c in batch]
        ids = [f"{source_type}_{filename}_{start+i}" for i in range(len(batch))]
        metas = [{
            "page": c["page"], "articles": c.get('articles', ''),
            "char_count": len(c['text']), "source_type": source_type, "source_file": filename,
            "article_key": c.get('article_key', ''),
            "article_content": c.get('article_content', ''),
        } for c in batch]
        try:
            collection.add(documents=docs, metadatas=metas, ids=ids)
        except Exception:
            for j in range(len(batch)):
                try: collection.add(documents=[docs[j]], metadatas=[metas[j]], ids=[ids[j]])
                except Exception: pass
        total += len(batch)
    print(f"  ✅ {filename} → {total} 条已入库")
    return total


def _auto_import():
    """扫描 data/law/ 和 data/sample/，跳过已导入的文件"""
    global chunks, bm25_index
    imported = _get_imported()
    new_count = 0

    for directory, label, stype in [(LAW_DIR, '法律', 'law'), (SAMPLE_DIR, '案例', 'sample')]:
        if not os.path.isdir(directory):
            continue
        # 支持 .pdf 和 .docx 格式
        pdfs = sorted([f for f in os.listdir(directory) if f.lower().endswith(('.pdf', '.docx'))])
        print(f"\n📂 {label}知识库 ({directory}): {len(pdfs)} 个文件")
        for f in pdfs:
            if f in imported:
                print(f"  ⏭️ {f} — 已导入")
                continue
            new_count += _import_one(os.path.join(directory, f), stype)

    if new_count > 0:
        all_data = collection.get(include=['documents', 'metadatas'])
        chunks = [{"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
                  for i in range(len(all_data['ids']))]
        bm25_index = BM25Okapi([list(jieba.cut(c["text"])) for c in chunks])
        print(f"\n✅ 导入完成 | 总量: {collection.count()} 条")


# ============================================================
# 混合检索 (BM25 + 向量语义 + RRF 融合)
# ============================================================

def hybrid_search(query, n_results=5, source_type: str = ""):
    """BM25关键词 + 向量语义 + RRF融合排序; source_type 可选 'law'/'sample'"""
    if not bm25_index or not collection:
        return []

    # 清理查询中的无效词（怎么/什么/如何等对BM25是噪声）
    stop_words = {'怎么', '什么', '如何', '哪些', '哪个', '多少', '是否',
                  '的', '了', '在', '是', '有', '和', '与', '或'}
    # 使用 cut_all 细粒度分词，避免"盗窃罪"无法匹配法条中单独的"盗窃"
    q_tokens = [t for t in jieba.cut(query, cut_all=True) if t.strip() and len(t) >= 1 and t not in stop_words]

    # 向量语义检索（复用 dpf_input.search_chunks）
    vec_raw = search_chunks(collection, query, n_results=20)
    vec_results = []
    for v in vec_raw:
        vec_results.append({
            "id": v.get('chunk_id', str(v)),
            "text": v["text"], "score": v.get("similarity", 0),
            "articles": v.get('articles', ''), "page": v.get('page', "?"),
            "source_file": v.get('source_file', ''),
            "source_type": v.get('source_type', ''),
            "article_key": v.get('article_key', ''),
            "article_content": v.get('article_content', ''),
        })

    # BM25 关键词检索（使用已过滤的 q_tokens）
    scores = bm25_index.get_scores(q_tokens) if q_tokens else np.zeros(len(chunks))
    top_idx = np.argsort(scores)[::-1][:20]

    bm25_results = []
    for idx in top_idx:
        c = chunks[idx]
        bm25_results.append({"id": c["id"], "text": c["text"],
                             "bm25_score": float(scores[idx]),
                             "articles": c.get('articles', ''), "page": c.get('page', '?'),
                             "source_file": c.get('source_file', ''),
                             "source_type": c.get('source_type', ''),
                             "article_key": c.get('article_key', ''),
                             "article_content": c.get('article_content', '')})

    # 按 source_type 过滤（如果指定）
    if source_type:
        vec_results = [r for r in vec_results if r.get("source_type") == source_type]
        bm25_results = [r for r in bm25_results if r.get("source_type") == source_type]

    # RRF 融合
    def rrf_score(rank): return 1.0 / (60 + rank + 1)
    score_map = {}
    for rank, r in enumerate(bm25_results):
        rid = r["id"]
        score_map[rid] = score_map.get(rid, {"item": r, "rrf": 0})
        score_map[rid]["rrf"] += rrf_score(rank)
    for rank, r in enumerate(vec_results):
        rid = r["id"]
        score_map[rid] = score_map.get(rid, {"item": r, "rrf": 0})
        score_map[rid]["rrf"] += rrf_score(rank)

    sorted_items = sorted(score_map.values(), key=lambda x: x["rrf"], reverse=True)[:n_results]
    for item in sorted_items:
        item["item"]["rrf_score"] = round(item["rrf"], 6)
    return [item["item"] for item in sorted_items]


# ============================================================
# CoT 法律推理 Prompt + LLM
# ============================================================

def ask_llm(prompt, api_key: str = "", base_url: str = "", model: str = ""):
    try:
        client = _make_client(api_key, base_url)
        resp = client.chat.completions.create(
            model=model or _DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048, temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠ LLM调用失败: {e}"


def build_legal_prompt(query, context):
    """统一 Prompt：结论在前 + 分析在后，通过 mode 控制细节"""
    is_simple = any(k in query for k in ['简要', '说明', '介绍', '是什么', '内容', '概括', '概述',
                                           '指导案例', '指导性案例', '案例'])
    # 结论要求
    conclusion_rule = (
        "- 简洁准确，无需冗长推理\n- 案例类需包含：案例名称、基本案情、裁判要点、裁判结果"
        if is_simple else
        "- 先说结论，明确回答用户问题\n- 分点列出关键要点，清晰易读"
    )
    # 分析要求
    analysis_rule = (
        "- 仅在需要展示推理依据时使用此段落\n- 列出引用的法条和逻辑推导过程"
        if is_simple else
        "- 识别涉及的法律关系\n- 逐条引用相关法条并分析\n- 说明推理逻辑和判断依据"
    )
    # 注意事项
    notes = (
        ""
        if is_simple else
        """【注意事项】
- 如果参考资料中没有完全匹配的内容，请在结论中说明"现有资料未涵盖此方面"
- 不要编造法条内容，仅基于给定资料作答
- 回答要专业、准确、有法律依据

""")
    return f"""你是一个专业的法律咨询助手。请基于以下参考资料回答用户问题。

【输出格式 — 严格遵守】
第一部分：直接给出答案（结论）
{conclusion_rule}

第二部分：【法律分析】
{analysis_rule}

【引用格式】
法条引用必须标注：【引用：《XX法》第X条】
案例引用必须标注：【引用：指导案例X号】

{notes}【参考资料】
{context}

【用户问题】
{query}

请严格按照上述格式输出："""


def format_for_llm(results):
    parts = []
    for i, item in enumerate(results, 1):
        arts = f"【条文: {item.get('articles', '')}】" if item.get('articles') else ""
        parts.append(f"[{i}] {arts} (第{item.get('page','?')}页)\n{item['text']}")
    return "\n\n".join(parts)


# ============================================================
# 挂载路由 + 启动
# ============================================================
from routes import router, init_routes


@app.on_event("startup")
def startup():
    init_chroma()
    # 将核心依赖注入路由模块
    init_routes({
        "collection": collection,
        "chunks": chunks,
        "bm25_index": bm25_index,
        "LAW_DIR": LAW_DIR,
        "SAMPLE_DIR": SAMPLE_DIR,
        "hybrid_search": hybrid_search,
        "ask_llm": ask_llm,
        "build_legal_prompt": build_legal_prompt,
        "format_for_llm": format_for_llm,
        "display_results": display_results,
        "get_imported": _get_imported,
        "import_one": _import_one,
    })
    app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
