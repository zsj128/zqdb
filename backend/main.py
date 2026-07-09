"""
智能法律咨询助手 - FastAPI 后端服务

核心流程:
  PDF → data_input.chunk_document分块 → ChromaDB入库
  用户问题 → search_chunks向量检索 + Jieba关键词匹配 → RRF融合排序 → CoT Prompt → 千问生成答案
"""
import os, warnings
import jieba
import openai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from routes import router, init_routes
from database import init_user_table

# 确保 backend 目录在搜索路径中
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in os.sys.path:
    os.sys.path.insert(0, _BACKEND_DIR)

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

app = FastAPI(title="智能法律咨询助手", version="1.0.0")#FastAPI 应用的初始化
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
#添加 CORS 中间件，允许跨域请求
#allow_origins=["*"] → 接受任意来源的前端请求，allow_methods=["*"] / allow_headers=["*"] → 放行所有 HTTP 方法和请求头
# 全局资源
collection = None
chunks = []
jieba_tokens = []  # 每个chunk的jieba分词结果(集合)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

STOP_WORDS = {'怎么', '什么', '如何', '哪些', '哪个', '多少', '是否',
              '的', '了', '在', '是', '有', '和', '与', '或','。','：','；','、'}

def _make_client(api_key: str = "", base_url: str = ""):
    """创建 OpenAI 兼容客户端"""
    return openai.OpenAI(
        api_key=api_key ,
        base_url=base_url or _DEFAULT_BASE_URL,
    )

# ============================================================
# ChromaDB 初始化 + 自动导入
# ============================================================

def init_chroma():
    """初始化 ChromaDB → 加载已有数据 → 扫描并导入新文件 → 构建Jieba分词索引"""
    global collection, chunks, jieba_tokens
    import chromadb
    import chromadb.utils.embedding_functions as ef_utils

    # ---- 1. 连接 DB ----
    embedding_fn = ef_utils.SentenceTransformerEmbeddingFunction(
        model_name='paraphrase-multilingual-MiniLM-L12-v2'
    )
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name='pdf_knowledge_base_v3',
        metadata={"description": "法律知识库", "hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    # ---- 2. 加载已有数据并构建 Jieba 分词索引 ----
    if collection.count() > 0:
        all_data = collection.get(include=['documents', 'metadatas'])
        chunks = [{"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
                  for i in range(len(all_data['ids']))]
        jieba_tokens = [set(t for t in jieba.cut(c["text"])
                   if t.strip() and len(t) >= 1 and t not in STOP_WORDS)
                   for c in chunks]
        print(f"ChromaDB 已加载: {collection.count()} 条数据, Jieba 分词索引已构建")

    # ---- 3. 扫描 & 导入新文件----
    imported = _get_imported()
    new_count = 0

    for directory, label, stype in [(LAW_DIR, '法律', 'law'), (SAMPLE_DIR, '案例', 'sample')]:
        if not os.path.isdir(directory):
            continue
        pdfs = sorted([f for f in os.listdir(directory) if f.lower().endswith(('.pdf', '.docx'))])
        print(f"\n📂 {label}知识库 ({directory}): {len(pdfs)} 个文件")
        for f in pdfs:
            if f in imported:
                print(f"  ⏭️ {f} — 已导入")
                continue
            new_count += _import_one(os.path.join(directory, f), stype)

    # ---- 4. 有新导入则刷新索引 ----
    if new_count > 0:
        all_data = collection.get(include=['documents', 'metadatas'])
        chunks = [{"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
                  for i in range(len(all_data['ids']))]
        jieba_tokens = [set(t for t in jieba.cut(c["text"])
                    if t.strip() and len(t) >= 1 and t not in STOP_WORDS)
                    for c in chunks]
        print(f"\n✅ 导入完成 | 总量: {collection.count()} 条")


def _get_imported():
    if not collection or collection.count() == 0:
        return set()
    return {m.get('source_file', '') for m in collection.get(include=['metadatas'])['metadatas'] if m.get('source_file')}


def _import_one(pdf_path, source_type):
    """解析单个文件F并入库"""
    filename = os.path.basename(pdf_path)
    print(f"  📄 解析 [{source_type}] {filename} ...")
    raw = chunk_document(pdf_path, source_type=source_type)
    total = 0
    for start in range(0, len(raw), 500):
        batch = raw[start:start + 500]
        docs = [c['text'] for c in batch]
        ids = [f"{source_type}_{filename}_{start+i}" for i in range(len(batch))]
        metas = [{
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

# ============================================================
# 混合检索 (Jieba关键词匹配 + 向量语义 + RRF 融合)
# ============================================================

def hybrid_search(query, n_results=5, source_type: str = ""):
    """Jieba关键词命中 + 向量语义 + RRF融合排序; source_type 可选 'law'/'sample'"""
    if not jieba_tokens or not collection:
        return []

    # Jieba 分词
    q_token_set = set(t for t in jieba.cut(query, cut_all=True)
                      if t.strip() and len(t) >= 1 and t not in STOP_WORDS)

    # 向量语义检索（复用 data_input.search_chunks）
    vec_raw = search_chunks(collection, query, n_results=20)
    vec_results = []
    for v in vec_raw:
        vec_results.append({
            "id": v.get('chunk_id', str(v)),
            "text": v["text"], "score": v.get("similarity", 0),
            "source_file": v.get('source_file', ''),
            "source_type": v.get('source_type', ''),
            "article_key": v.get('article_key', ''),
            "article_content": v.get('article_content', ''),
        })

    # Jieba 关键词命中计数排序
    hit_scores = []
    for i, ct in enumerate(jieba_tokens):
        hit_count = len(q_token_set & ct)  # 命中词数，求交集
        if hit_count > 0:
            hit_scores.append((hit_count, i))

    hit_scores.sort(key=lambda x: x[0], reverse=True)
    jieba_results = []
    for hit_count, idx in hit_scores[:20]:
        c = chunks[idx]
        jieba_results.append({"id": c["id"], "text": c["text"],
                              "jieba_hits": hit_count,
                              "articles": c.get('articles', ''), "page": c.get('page', '?'),
                              "source_file": c.get('source_file', ''),
                              "source_type": c.get('source_type', ''),
                              "article_key": c.get('article_key', ''),
                              "article_content": c.get('article_content', '')})

    # 按 source_type 过滤（如果指定）
    if source_type:
        vec_results = [r for r in vec_results if r.get("source_type") == source_type]
        jieba_results = [r for r in jieba_results if r.get("source_type") == source_type]

    # RRF 融合：将Jieba 关键词命中和向量语义检索融合
    def rrf_score(rank): return 1.0 / (60 + rank + 1)
    score_map = {}
    for rank, r in enumerate(jieba_results):
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
# 法律推理 Prompt + LLM
# ============================================================

def ask_llm(prompt, api_key: str = "", base_url: str = "", model: str = ""):
    try:
        client = _make_client(api_key, base_url)
        resp = client.chat.completions.create(
            model=model ,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096, temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠ 大模型调用失败: {e}"


def build_legal_prompt(query, context):
    """统一 Prompt：结论在前 + 分析在后，通过 mode 控制细节"""
    # 结论要求
    conclusion_rule = (
    """- 如果是法律案例分析之类的：简洁准确，无需冗长推理\n- 案例类需包含：案例名称、基本案情、裁判要点、裁判结果
       - 如果是法律问题解答：先说结论，明确回答用户问题\n- 分点列出关键要点，清晰易读"""
    )
    # 分析要求
    analysis_rule = (
    """- 如果是法律案例分析之类的：仅在需要展示推理依据时使用此段落\n- 列出引用的法条和逻辑推导过程
       - 如果是法律问题解答：识别涉及的法律关系\n- 逐条引用相关法条并分析\n- 说明推理逻辑和判断依据"""
    )
    # 注意事项
    notes = (
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

    【法律问题解答时】
    {notes}

    【参考资料】
    {context}

    【用户问题】
    {query}

    请严格按照上述格式输出："""


def format_for_llm(results):
    parts = []
    for i, item in enumerate(results, 1):
        arts = f"【条文: {item.get('articles', '')}】" if item.get('articles') else ""
        parts.append(f"[{i}] {arts}\n{item['text']}")
    return "\n\n".join(parts)


# ============================================================
# 挂载路由 + 启动
# ============================================================

@app.on_event("startup")
def startup():
    init_user_table()  # 初始化用户数据库
    init_chroma()
    # 将核心依赖注入路由模块
    init_routes({
        "collection": collection,
        "chunks": chunks,
        "jieba_tokens": jieba_tokens,
        "LAW_DIR": LAW_DIR,
        "SAMPLE_DIR": SAMPLE_DIR,
        "hybrid_search": hybrid_search,
        "ask_llm": ask_llm,
        "build_legal_prompt": build_legal_prompt,
        "format_for_llm": format_for_llm,
        "display_results": display_results,
    })
    app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
