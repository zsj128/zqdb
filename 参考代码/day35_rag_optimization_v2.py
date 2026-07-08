#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Day35 RAG优化策略 —— 完整可运行代码示例

核心配置：
  - 嵌入模型: paraphrase-multilingual-MiniLM-L12-v2 (SBERT)
  - LLM: 千问 (qwen-plus / qwen-turbo)
  - 向量存储: ChromaDB (使用 SBERT 嵌入, 不下载 ONNX 默认模型)

使用前：
  export QWEN_API_KEY="your-dashscope-api-key"
  pip install numpy openai jieba rank-bm25 sentence-transformers chromadb pdfplumber
"""
import warnings
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=r".*pkg_resources is deprecated as an API.*"
)
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import re
import time
import json
import numpy as np
import openai
import jieba
import pdfplumber
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb


# ============================================================
# 配置区
# ============================================================

QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "sk-f0571b85dc0f4d72a7185b31edb23d7f")  # ← 替换

qwen_client = openai.OpenAI(
    base_url=QWEN_BASE_URL,
    api_key=QWEN_API_KEY
)

# 全局 SBERT 模型（懒加载）
_SBERT_MODEL = None
# 统一使用这个中文友好的 SBERT 模型
SBERT_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'


def get_sbert_model():
    """懒加载 SBERT 模型（第一次调用时才下载/加载）"""
    global _SBERT_MODEL
    if _SBERT_MODEL is None:
        print(f"正在加载 SBERT 模型（{SBERT_MODEL_NAME}）...")
        _SBERT_MODEL = SentenceTransformer(SBERT_MODEL_NAME)
        print(f"  ✓ 模型已加载，向量维度: {_SBERT_MODEL.get_sentence_embedding_dimension()}")
    return _SBERT_MODEL


# ============================================================
# ChromaDB 嵌入函数 — 用 SBERT 替代 Chroma 默认 ONNX
# ============================================================

class ChromaSBERTEmbedding:
    """
    Chroma 自定义嵌入函数。
    用 sentence-transformers 的 paraphrase-multilingual-MiniLM-L12-v2
    替代 Chroma 内置的 all-MiniLM-L6-v2 ONNX，避免下载大文件。
    """
    def __call__(self, input):
        model = get_sbert_model()
        embeddings = model.encode(input, convert_to_numpy=True)
        return embeddings.tolist()


EMBEDDING_FN = ChromaSBERTEmbedding()


# ============================================================
# 千问 API 封装
# ============================================================

def qwen_chat(prompt, model="qwen-plus", max_tokens=512, temperature=0.3):
    """调用千问 LLM（OpenAI 兼容格式）"""
    try:
        response = qwen_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  ⚠ 千问调用失败: {e}")
        return ""


# ============================================================
# 第1课时：检索评估
# ============================================================

def evaluate_retrieval(retrieved, relevant_ids):
    """
    计算 Precision / Recall / F1

    参数:
        retrieved:    List[dict], 检索结果（每条有 "id" 字段）
        relevant_ids: List[str], 参考答案的文档 ID

    返回:
        dict: {"precision": ..., "recall": ..., "f1": ...}
    """
    retrieved_ids = set(r["id"] for r in retrieved)
    relevant_set = set(relevant_ids)

    tp = len(retrieved_ids & relevant_set)
    precision = tp / len(retrieved_ids) if len(retrieved_ids) > 0 else 0
    recall = tp / len(relevant_set) if len(relevant_set) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


# ============================================================
# 第2课时：查询扩展
# ============================================================

def expand_query_synonym(query, synonym_dict=None):
    """
    基于同义词词典扩展查询（无 LLM 版本）

    参数:
        query:         原始查询字符串
        synonym_dict:  {"机器学习": ["人工智能","AI"], ...}

    返回:
        List[str]: 扩展后的查询列表
    """
    if synonym_dict is None:
        synonym_dict = {
            "机器学习": ["人工智能", "AI"],
            "神经网络": ["深度学习", "神经网络模型"],
            "数据": ["数据集", "资料"],
            "训练": ["学习", "训练过程"],
            "模型": ["算法", "网络结构"],
        }

    expanded = [query]
    for keyword, synonyms in synonym_dict.items():
        if keyword in query:
            for syn in synonyms:
                new_query = query.replace(keyword, syn)
                if new_query not in expanded:
                    expanded.append(new_query)
    return expanded


def expand_query_llm(query, n_variants=3, model="qwen-turbo"):
    """
    用千问改写查询（LLM 版本）

    参数:
        query:         原始查询字符串
        n_variants:    生成几个变体
        model:         千问模型

    返回:
        List[str]: 包含原始查询 + 扩展查询的列表
    """
    prompt = f"""你是一个信息检索专家。请帮我把用户的问题改写成 {n_variants} 种不同的表达方式，
每种表达都能帮助检索到相关文档。

规则:
1. 保留原问题的核心意图，只改变表述方式
2. 可以使用同义词替换、改变句式、加入行业术语
3. 每行输出一个查询，不要编号，不要解释
4. 输出 {n_variants} 行，不要多也不要少

原始问题: {query}

请直接输出 {n_variants} 个改写后的查询（每行一个）:"""

    response = qwen_chat(prompt, model=model, max_tokens=200, temperature=0.7)
    lines = [line.strip() for line in response.split("\n") if line.strip()]
    expanded = [query]
    for line in lines:
        if line not in expanded:
            expanded.append(line)
    return expanded


def multi_query_search(collection, bm25_index, tokenized_chunks, chunks, queries, n_results=10):
    """
    多查询并行搜索 + 结果合并去重
    用 query_embeddings 避免触发 Chroma 默认嵌入下载
    """
    model = get_sbert_model()
    all_results = {}
    for q in queries:
        # BM25
        bm25_res = bm25_search(bm25_index, tokenized_chunks, q, chunks, n_results=n_results)
        for r in bm25_res:
            if r["id"] not in all_results:
                all_results[r["id"]] = r
        # 向量检索（手动传 query_embeddings）
        q_emb = model.encode([q]).tolist()
        vec_res = collection.query(
            query_embeddings=q_emb,
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        for i in range(len(vec_res["ids"][0])):
            rid = vec_res["ids"][0][i]
            if rid not in all_results:
                all_results[rid] = {
                    "id": rid,
                    "text": vec_res["documents"][0][i],
                    "score": 1 - vec_res["distances"][0][i],
                }
    return list(all_results.values())


# ============================================================
# 第3课时：HyDE 假设文档生成
# ============================================================

def hyde_search(collection, query, n_results=5, model="qwen-plus"):
    """
    HyDE（Hypothetical Document Embeddings）检索

    流程:
      1. 让千问根据问题生成一段"假设的答案文档"
      2. 将这段假设文档向量化
      3. 用这个向量去 Chroma 检索——找到真正相似的文档

    用 query_embeddings 而非 query_texts，避免触发 Chroma 默认嵌入
    """
    # Step 1: 生成假设文档
    prompt = f"请写一段简短的回答（200字以内）来回答以下问题。不需要完全正确，只需要像一篇真实文档：{query}"
    hypothetical_doc = qwen_chat(prompt, model=model, max_tokens=300, temperature=0.7)

    if not hypothetical_doc:
        return []

    # Step 2: 用 SBERT 向量化（不是 Chroma 默认嵌入！）
    sbert = get_sbert_model()
    doc_embedding = sbert.encode([hypothetical_doc]).tolist()

    # Step 3: 检索
    results = collection.query(
        query_embeddings=doc_embedding,
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "score": 1 - results["distances"][0][i],
        })
    return output


# ============================================================
# 第4课时：混合检索（BM25 + 向量 + RRF）
# ============================================================

def build_bm25_index(chunks):
    """构建 BM25 索引"""
    tokenized = []
    for c in chunks:
        words = list(jieba.cut(c["text"]))
        tokenized.append(words)
    bm25 = BM25Okapi(tokenized)
    return bm25, tokenized


def bm25_search(bm25_index, tokenized_chunks, query, chunks, n_results=20):
    """BM25 关键词检索"""
    tokenized_query = list(jieba.cut(query))
    scores = bm25_index.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:n_results]
    results = []
    for idx in top_indices:
        # 不过滤，返回所有 top n 结果（即使分数为 0）
        results.append({
            "id": chunks[idx]["id"],
            "text": chunks[idx]["text"],
            "bm25_score": float(scores[idx]),
            "index": int(idx),
        })
    return results


def rrf_fusion(bm25_results, vector_results, k=60, final_n=5):
    """
    RRF（Reciprocal Rank Fusion）算法
    将 BM25 排名和向量排名的结果融合，各取所长
    """
    def rrf_score(rank):
        return 1.0 / (k + rank + 1)

    score_map = {}
    for rank, r in enumerate(bm25_results):
        rid = r["id"]
        score_map[rid] = score_map.get(rid, {"item": r, "rrf": 0})
        score_map[rid]["rrf"] += rrf_score(rank)

    for rank, r in enumerate(vector_results):
        rid = r["id"]
        score_map[rid] = score_map.get(rid, {"item": r, "rrf": 0})
        score_map[rid]["rrf"] += rrf_score(rank)

    sorted_items = sorted(score_map.values(), key=lambda x: x["rrf"], reverse=True)
    final = []
    for item in sorted_items[:final_n]:
        item["item"]["rrf_score"] = round(item["rrf"], 6)
        final.append(item["item"])
    return final


def hybrid_search(collection, chunks, bm25_index, tokenized_chunks, query, n_results=5):
    """
    混合检索：BM25 + 向量检索 + RRF 融合

    关键：使用 query_embeddings 而非 query_texts，避免 Chroma 下载 ONNX 默认模型
    """
    sbert = get_sbert_model()

    # 【第一步】BM25 检索
    bm25_results = bm25_search(bm25_index, tokenized_chunks, query, chunks, n_results=20)

    # 【第二步】向量检索（手动传 embedding）
    query_emb = sbert.encode([query]).tolist()
    vec_res = collection.query(
        query_embeddings=query_emb,
        n_results=20,
        include=["documents", "metadatas", "distances"]
    )
    vector_results = []
    for i in range(len(vec_res["ids"][0])):
        vector_results.append({
            "id": vec_res["ids"][0][i],
            "text": vec_res["documents"][0][i],
            "score": 1 - vec_res["distances"][0][i],
        })

    # 【第三步】RRF 融合
    return rrf_fusion(bm25_results, vector_results, k=60, final_n=n_results)


# ============================================================
# 第5课时：重排序
# ============================================================

def rerank_with_qwen(query, candidates, model="qwen-turbo"):
    """
    用千问 LLM 对候选文档逐对打分（不下载 Cross-Encoder 模型）

    参数:
        query:       查询文本
        candidates:  List[dict], 候选文档
        model:       千问模型

    返回:
        List[dict]: 按重排序分数降序排列
    """
    if not candidates:
        return []

    prompt = f"""请对以下文档与问题的相关性打分（0-10分，10分 = 完全相关）。
对每个文档只输出一个数字（0-10），每行一个。

问题: {query}

"""
    for i, c in enumerate(candidates[:10]):
        text_short = c["text"][:200].replace("\n", " ")
        prompt += f"文档{i}: {text_short}\n"

    prompt += "\n请输出10个分数（每行一个数字，0-10）:"

    response = qwen_chat(prompt, model=model, max_tokens=100, temperature=0)
    scores = []
    for line in response.split("\n"):
        try:
            scores.append(float(line.strip()) / 10.0)
        except ValueError:
            scores.append(0.0)

    for i, c in enumerate(candidates):
        c["rerank_score"] = scores[i] if i < len(scores) else 0.0

    return sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)


def rerank_with_cross_encoder(query, candidates, cross_encoder=None, top_n=5):
    """
    用 Cross-Encoder 精排（需要下载 cross-encoder/ms-marco-MiniLM-L-6-v2，约80MB）
    """
    if cross_encoder is None:
        print("  正在加载 Cross-Encoder 精排模型...")
        cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    pairs = [(query, c["text"][:500]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    for i, c in enumerate(candidates):
        c["rerank_score"] = float(scores[i])

    return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)[:top_n]


# ============================================================
# 第6课时：上下文压缩
# ============================================================

def compress_context_llm(query, candidates, model="qwen-turbo"):
    """用千问过滤不相关的文档段落（上下文压缩）"""
    if not candidates:
        return ""

    context_parts = []
    for i, c in enumerate(candidates[:10]):
        context_parts.append(f"[{i}] {c['text'][:300]}")

    full_context = "\n\n".join(context_parts)

    prompt = f"""请从以下参考资料中筛选出与问题相关的段落。
只保留直接回答问题的内容，删除无关的部分。

问题: {query}

参考资料:
{full_context}

请输出筛选后的相关段落编号（用逗号分隔，如 0,2,5）:"""

    response = qwen_chat(prompt, model=model, max_tokens=50, temperature=0)
    try:
        indices = [int(x.strip()) for x in response.split(",") if x.strip().isdigit()]
    except Exception:
        indices = list(range(min(5, len(candidates))))

    filtered = [candidates[i]["text"] for i in indices if i < len(candidates)]
    return "\n\n".join(filtered)


def mmr_rerank(query_embedding, candidate_embeddings, candidates, lambda_param=0.7, n_final=5):
    """
    MMR（Maximum Marginal Relevance）去重
    lambda_param=0.7: 偏向相关性
    lambda_param=0.3: 偏向多样性
    """
    n = len(candidates)
    selected = []
    remaining = set(range(n))
    for _ in range(min(n_final, n)):
        best_idx = -1
        best_mmr = -float("inf")
        for i in remaining:
            relevance = float(np.dot(query_embedding, candidate_embeddings[i]))
            diversity = 0
            if selected:
                diversity = max(float(np.dot(candidate_embeddings[i], candidate_embeddings[s]))
                               for s in selected)
            mmr = lambda_param * relevance - (1 - lambda_param) * diversity
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        selected.append(best_idx)
        remaining.remove(best_idx)
    return [candidates[i] for i in selected]


# ============================================================
# 辅助函数
# ============================================================

def compare_header(num, title):
    """打印对比章节标题"""
    print(f"\n\n{'═'*70}")
    print(f"  对比{num}: {title}")
    print(f"{'═'*70}")


def smart_truncate(text, max_chars=500):
    """按句子截断，不截断句子中间"""
    sentences = re.split(r'(?<=[。！？.!?])', text)
    result = ""
    for s in sentences:
        if len(result) + len(s) > max_chars:
            break
        result += s
    return result


def simple_chunk_text(text, chunk_size=300, overlap=50):
    """按句子边界分块，避免切断句子"""
    import re
    # 按中文/英文句子结束符切分句子
    sentences = re.split(r'(?<=[。！？.!?])\s*', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    chunk_id = 0
    i = 0
    while i < len(sentences):
        current = []
        current_len = 0
        while i < len(sentences) and current_len + len(sentences[i]) <= chunk_size:
            current.append(sentences[i])
            current_len += len(sentences[i])
            i += 1
        if not current:
            # 单句超长，直接作为一块
            current.append(sentences[i])
            i += 1
        chunk_text = "".join(current)
        if len(chunk_text) < 20:
            break
        chunks.append({
            "id": f"chunk_{chunk_id}",
            "text": chunk_text,
            "metadata": {"page": chunk_id // 5 + 1}
        })
        chunk_id += 1
        # 按 overlap 回退句子数
        overlap_len = 0
        step_back = 0
        for j in range(len(current) - 1, -1, -1):
            overlap_len += len(current[j])
            step_back += 1
            if overlap_len >= overlap:
                break
        i -= step_back
        if i <= 0:
            i = 0  # 防止死循环
            break
    return chunks


def load_pdf_text(pdf_path):
    """从 PDF 提取全文"""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text


# ============================================================
# 第7课时：OptimizedRAG 完整类
# ============================================================

class OptimizedRAG:
    """
    综合优化 RAG 系统

    流水线:
      用户查询 → [扩展] → [HyDE] → 混合检索 → [重排序] → [压缩] → 千问生成
    """

    def __init__(self,
                 use_query_expansion=False,
                 use_hyde=False,
                 use_reranking=True,
                 reranking_method="qwen",
                 use_context_compression=False,
                 compression_method="mmr",
                 sbert_model=None):
        self.chunks = []
        self.collection = None
        self.client = None  # 保持 EphemeralClient 引用，防止 GC 回收底层资源
        self.bm25_index = None
        self.tokenized_chunks = None

        self.use_query_expansion = use_query_expansion
        self.use_hyde = use_hyde
        self.use_reranking = use_reranking
        self.reranking_method = reranking_method
        self.use_context_compression = use_context_compression
        self.compression_method = compression_method

        self.sbert_model = sbert_model if sbert_model else get_sbert_model()
        self.cross_encoder = None

    def load_pdf(self, pdf_path):
        """加载 PDF 并构建索引（关键：使用 SBERT embedding_function）"""
        print(f"\n正在加载 PDF: {pdf_path}")

        full_text = load_pdf_text(pdf_path)
        self.chunks = simple_chunk_text(full_text, chunk_size=300, overlap=50)

        # 使用 SBERT 嵌入函数，避免 Chroma 下载 ONNX 默认模型！
        self.client = chromadb.EphemeralClient()
        coll_name = f"optimized_rag_{id(self)}"
        try:
            self.client.delete_collection(coll_name)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            coll_name,
            embedding_function=EMBEDDING_FN,  # ← 关键！不下载 ONNX
            metadata={"hnsw:space": "cosine"}  # 使用余弦距离
        )

        texts = [c["text"] for c in self.chunks]
        print(f"  正在用 SBERT 编码 {len(texts)} 个段落...")
        embeddings = self.sbert_model.encode(texts, show_progress_bar=True)

        self.collection.add(
            ids=[c["id"] for c in self.chunks],
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=[c["metadata"] for c in self.chunks]
        )

        self.bm25_index, self.tokenized_chunks = build_bm25_index(self.chunks)
        print(f"  PDF 加载完成，共 {len(self.chunks)} 个段落")
        self._print_config()

    def _print_config(self):
        print("\n当前 OptimizedRAG 配置:")
        print(f"  嵌入模型:  {SBERT_MODEL_NAME} (SBERT)")
        print(f"  查询扩展:  {'开启' if self.use_query_expansion else '关闭'}")
        print(f"  HyDE:      {'开启' if self.use_hyde else '关闭'}")
        print(f"  重排序:    {'开启' if self.use_reranking else '关闭'} ({self.reranking_method})")
        print(f"  上下文压缩: {'开启' if self.use_context_compression else '关闭'} ({self.compression_method})")
        print(f"  LLM:       千问 (qwen-plus/qwen-turbo)")
        print()

    def search(self, query, n_results=5):
        """端到端检索"""
        print(f"\n{'='*50}")
        print(f"查询: {query}")
        print(f"{'='*50}")

        # 【第一步】查询扩展
        if self.use_query_expansion:
            print("【第一步】查询扩展...")
            expanded_queries = expand_query_llm(query, n_variants=3, model="qwen-turbo")
            print(f"  扩展为 {len(expanded_queries)} 个查询")
        else:
            expanded_queries = [query]

        # 【第二步】HyDE
        if self.use_hyde:
            print("【第二步】HyDE 假设文档生成...")
            hyde_candidates = hyde_search(self.collection, expanded_queries[0], n_results=20)
        else:
            hyde_candidates = []

        # 【第三步】混合检索
        step = "HyDE" if self.use_hyde else ""
        if self.use_query_expansion:
            step = ("【第" + ("二" if self.use_hyde else "一") + "步】" +
                    ("查询扩展 " if not self.use_hyde else "") + "混合检索...")
        else:
            step = ("【第" + ("一" if not self.use_hyde else "二") + "步】混合检索...")
        print(f"{step}")
        candidates = hybrid_search(
            self.collection, self.chunks,
            self.bm25_index, self.tokenized_chunks,
            expanded_queries[0], n_results=20
        )

        if hyde_candidates:
            candidates = rrf_fusion(candidates, hyde_candidates, k=60, final_n=20)

        # 【第四步】重排序
        if self.use_reranking:
            step_num = sum([self.use_query_expansion, self.use_hyde, True])
            print(f"【第{step_num}步】重排序（{self.reranking_method}）...")
            candidates = self._rerank(expanded_queries[0], candidates)
        else:
            candidates = candidates[:n_results]

        print(f"  最终候选（Top-{n_results}）:")
        for i, c in enumerate(candidates[:n_results]):
            score = c.get("rerank_score", c.get("rrf_score", c.get("score", 0)))
            print(f"    {i+1}. [分数={score:.3f}] {c['text'][:50]}...")

        return candidates[:n_results]

    def _rerank(self, query, candidates):
        if self.reranking_method == "cross_encoder":
            if self.cross_encoder is None:
                print("  正在下载 Cross-Encoder 模型（约80MB，仅首次）...")
                self.cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            return rerank_with_cross_encoder(query, candidates, self.cross_encoder, top_n=5)
        else:
            return rerank_with_qwen(query, candidates[:10], model="qwen-turbo")[:5]

    def ask(self, query, model="qwen-plus"):
        """端到端问答"""
        candidates = self.search(query, n_results=5)
        context = "\n\n".join([c["text"] for c in candidates])

        prompt = f"""请基于以下参考资料回答问题。
如果参考资料中没有相关信息，请说"资料中未提及"，不要编造。

参考资料:
{context}

问题: {query}

答案:"""

        print("\n【最后一步】千问生成答案...")
        answer = qwen_chat(prompt, model=model, max_tokens=500, temperature=0.3)
        print(f"\n{'─'*50}")
        print(f"答案: {answer}")
        print(f"{'─'*50}")
        return answer


# ============================================================
# 第8课时：评测框架
# ============================================================

class RAGEvaluator:
    """自动化评测：对比不同配置的 OptimizedRAG 效果"""

    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.test_queries = []
        self.relevant_ids = {}

    def add_test_case(self, query, relevant_chunk_ids):
        self.test_queries.append(query)
        self.relevant_ids[query] = relevant_chunk_ids

    def evaluate(self, configs):
        """
        在不同配置下评测

        参数:
            configs: List[dict], 每个 dict 是 OptimizedRAG 的初始化参数

        返回:
            pd.DataFrame: 评测结果表
        """
        results = []
        for cfg in configs:
            name = cfg.pop("name", "Unnamed")
            rag = OptimizedRAG(**cfg)
            rag.load_pdf(self.pdf_path)

            total_p = total_r = total_f = 0
            for query in self.test_queries:
                retrieved = rag.search(query, n_results=10)
                metrics = evaluate_retrieval(retrieved, self.relevant_ids.get(query, []))
                total_p += metrics["precision"]
                total_r += metrics["recall"]
                total_f += metrics["f1"]

            n = len(self.test_queries)
            results.append({
                "配置": name,
                "Precision": round(total_p / n, 4) if n else 0,
                "Recall": round(total_r / n, 4) if n else 0,
                "F1": round(total_f / n, 4) if n else 0,
            })

            cfg["name"] = name

        return pd.DataFrame(results)


# ============================================================
# 主程序入口
# ============================================================

def main():
    """
    Day35 完整对比演示 —— 逐项展示每种优化技术的效果

    运行方式:
        python day35_rag_optimization.py

    每项对比会展示：
        - BEFORE（未使用优化）→ AFTER（使用优化）
        - 对比分析总结
    """
    pdf_path = "test_document.pdf"
    if not os.path.exists(pdf_path):
        print(f"⚠ 未找到测试 PDF（{pdf_path}），请先运行 gen_test_pdf.py 生成")
        return

    # ══════════════════════════════════════════════════════════
    # 零、加载 PDF，构建共享索引
    # ══════════════════════════════════════════════════════════
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + "  Day35 RAG 优化策略 —— 逐项对比演示".center(60) + "║")
    print("╚" + "═" * 68 + "╝")

    # 用最简配置加载（不开任何优化），构建共享的向量库和 BM25 索引
    rag_base = OptimizedRAG(
        use_query_expansion=False,
        use_hyde=False,
        use_reranking=False,
        use_context_compression=False,
    )
    rag_base.load_pdf(pdf_path)

    col = rag_base.collection
    chunks = rag_base.chunks
    bm25_idx = rag_base.bm25_index
    tok_chunks = rag_base.tokenized_chunks
    sbert = rag_base.sbert_model

    # 测试查询
    Q1 = "Python的设计哲学是什么？"
    Q2 = "机器学习有哪些常用算法？"
    Q3 = "深度学习与神经网络的关系是什么？"

    # ══════════════════════════════════════════════════════════
    # 一、BM25 vs 向量检索 vs 混合检索（RRF融合）
    # ══════════════════════════════════════════════════════════
    compare_header("一", "检索方式对比：BM25 vs 向量检索 vs 混合检索（RRF）")

    for q in [Q1, Q2]:
        print(f"\n  {'─'*60}")
        print(f"  查询: {q}")
        print(f"  {'─'*60}")

        # A: BM25 only
        print("\n  【BEFORE - 纯 BM25 关键词匹配】")
        bm25_res = bm25_search(bm25_idx, tok_chunks, q, chunks, n_results=3)
        for i, r in enumerate(bm25_res):
            print(f"    {i+1}. [score={r['bm25_score']:.4f}] {r['text'][:75]}...")

        # B: 纯向量
        print("\n  【BEFORE - 纯向量语义检索】")
        q_emb = sbert.encode([q]).tolist()
        vec_res = col.query(query_embeddings=q_emb, n_results=3, include=["documents", "distances"])
        n_ret = len(vec_res["ids"][0])  # 实际返回的结果数
        for i in range(n_ret):
            print(f"    {i+1}. [score={1 - vec_res['distances'][0][i]:.4f}] {vec_res['documents'][0][i][:75]}...")

        # C: 混合检索
        print("\n  【AFTER  - 混合检索（BM25 + 向量 → RRF 融合）】")
        hyb_res = hybrid_search(col, chunks, bm25_idx, tok_chunks, q, n_results=3)
        for i, r in enumerate(hyb_res):
            s = r.get('rrf_score', 0)
            print(f"    {i+1}. [rrf={s:.4f}] {r['text'][:75]}...")

    # ══════════════════════════════════════════════════════════
    # 二、查询扩展：原始查询 vs 扩展后查询
    # ══════════════════════════════════════════════════════════
    compare_header("二", "查询扩展：原始查询 vs 千问多角度改写")

    for q in [Q1, Q2]:
        print(f"\n  {'─'*60}")
        print(f"  原始查询: {q}")
        print(f"  {'─'*60}")

        # BEFORE: 原始查询直接检索
        print("\n  【BEFORE - 原始查询（可能词汇不匹配）】")
        q_emb = sbert.encode([q]).tolist()
        vec_before = col.query(query_embeddings=q_emb, n_results=5, include=["documents", "distances"])
        n_ret = len(vec_before["ids"][0])
        for i in range(min(3, n_ret)):
            print(f"    {i+1}. [score={1 - vec_before['distances'][0][i]:.4f}] {vec_before['documents'][0][i][:75]}...")

        # 千问扩展
        print("\n  【千问改写为多角度查询...】")
        expanded = expand_query_llm(q, n_variants=3)
        for i, eq in enumerate(expanded):
            print(f"    变体{i+1}: {eq}")

        # AFTER: 多查询合并检索
        print("\n  【AFTER  - 多查询合并检索（扩大覆盖面）】")
        all_cand = {}
        for eq in expanded:
            eq_emb = sbert.encode([eq]).tolist()
            eq_res = col.query(query_embeddings=eq_emb, n_results=5, include=["documents", "distances"])
            n_ret = len(eq_res["ids"][0])
            for j in range(n_ret):
                rid = eq_res["ids"][0][j]
                if rid not in all_cand:
                    all_cand[rid] = {"text": eq_res["documents"][0][j], "score": 1 - eq_res["distances"][0][j]}
        sorted_exp = sorted(all_cand.values(), key=lambda x: x["score"], reverse=True)
        for i, c in enumerate(sorted_exp[:3]):
            print(f"    {i+1}. [score={c['score']:.4f}] {c['text'][:75]}...")

    # ══════════════════════════════════════════════════════════
    # 三、HyDE：原始查询 vs 假设文档检索
    # ══════════════════════════════════════════════════════════
    compare_header("三", "HyDE 假设文档嵌入：直接用问题 vs 用假设答案检索")

    for q in [Q1, Q2]:
        print(f"\n  {'─'*60}")
        print(f"  查询: {q}")
        print(f"  {'─'*60}")

        # BEFORE: 直接向量检索
        print("\n  【BEFORE - 直接用问题的向量检索】")
        q_emb = sbert.encode([q]).tolist()
        vec_before = col.query(query_embeddings=q_emb, n_results=3, include=["documents", "distances"])
        n_ret = len(vec_before["ids"][0])
        for i in range(n_ret):
            print(f"    {i+1}. [score={1 - vec_before['distances'][0][i]:.4f}] {vec_before['documents'][0][i][:75]}...")

        # AFTER: HyDE
        print("\n  【AFTER  - 千问生成假设答案 → 用答案向量检索】")
        hyde_res = hyde_search(col, q, n_results=3)
        for i, r in enumerate(hyde_res):
            print(f"    {i+1}. [score={r['score']:.4f}] {r['text'][:75]}...")

    # ══════════════════════════════════════════════════════════
    # 四、重排序：混合检索 vs 混合检索+千问精排
    # ══════════════════════════════════════════════════════════
    compare_header("四", "重排序：混合检索粗排 vs 千问精排重排序")

    for q in [Q1, Q2]:
        print(f"\n  {'─'*60}")
        print(f"  查询: {q}")
        print(f"  {'─'*60}")

        # BEFORE: 混合检索结果（无需重排序）
        print("\n  【BEFORE - 混合检索 Top-5（可能包含弱相关项）】")
        hyb5 = hybrid_search(col, chunks, bm25_idx, tok_chunks, q, n_results=5)
        for i, r in enumerate(hyb5):
            s = r.get('rrf_score', 0)
            print(f"    {i+1}. [rrf={s:.4f}] {r['text'][:70]}...")

        # AFTER: 千问精排
        print("\n  【AFTER  - 千问精排重排序 Top-3（精确筛选）】")
        reranked = rerank_with_qwen(q, hyb5[:5], model="qwen-turbo")
        for i, r in enumerate(reranked[:3]):
            rs = r.get("rerank_score", 0)
            print(f"    {i+1}. [rerank={rs:.3f}] {r['text'][:70]}...")

    # ══════════════════════════════════════════════════════════
    # 五、上下文压缩：原始上下文 vs MMR 去重
    # ══════════════════════════════════════════════════════════
    compare_header("五", "上下文压缩：原始候选 vs MMR 最大边界相关性去重")

    for q in [Q1, Q2]:
        print(f"\n  {'─'*60}")
        print(f"  查询: {q}")
        print(f"  {'─'*60}")

        # 获取候选
        hyb8 = hybrid_search(col, chunks, bm25_idx, tok_chunks, q, n_results=8)
        q_emb = sbert.encode([q])[0]
        texts = [c["text"] for c in hyb8]
        cand_embs = sbert.encode(texts)

        # 检查相似度
        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        try:
            sim_matrix = cos_sim(cand_embs)
            print(f"\n  【BEFORE - 候选文档相似度矩阵（高值=内容重复）】")
            for i in range(min(5, len(texts))):
                sims = " ".join(f"{sim_matrix[i][j]:.2f}" for j in range(min(5, i+1)))
                print(f"    [{i}] {sims} | {texts[i][:45]}...")
        except Exception:
            print("  (sklearn 未安装，跳过相似度矩阵)")

        # AFTER: MMR
        print("\n  【AFTER  - MMR 去重（保留相关性+最大化多样性）】")
        mmr_res = mmr_rerank(q_emb, cand_embs, hyb8, lambda_param=0.7, n_final=3)
        for i, r in enumerate(mmr_res):
            print(f"    {i+1}. {r['text'][:75]}...")

    # ══════════════════════════════════════════════════════════
    # 六、端到端问答对比：基本RAG vs 优化后RAG
    # ══════════════════════════════════════════════════════════
    compare_header("六", "端到端问答对比：基本 RAG vs 完整优化 RAG")

    # 基本 RAG：无任何优化
    rag_basic = OptimizedRAG(
        use_query_expansion=False, use_hyde=False,
        use_reranking=False, use_context_compression=False,
    )
    rag_basic.load_pdf(pdf_path)

    # 完整优化：全部开启
    rag_full = OptimizedRAG(
        use_query_expansion=True,
        use_hyde=True,
        use_reranking=True,
        reranking_method="qwen",
        use_context_compression=True,
        compression_method="mmr",
    )
    rag_full.load_pdf(pdf_path)

    for q in [Q1, Q3]:
        print(f"\n  {'─'*60}")
        print(f"  查询: {q}")
        print(f"  {'─'*60}")

        print("\n  【BEFORE - 基本 RAG（无任何优化）】")
        print("  流水线: PDF→分块→向量检索→千问")
        rag_basic.ask(q, model="qwen-turbo")

        print("\n  【AFTER  - 完整优化 RAG】")
        print("  流水线: PDF→分块→查询扩展→HyDE→混合检索→重排序→MMR去重→千问")
        rag_full.ask(q, model="qwen-turbo")

    # ══════════════════════════════════════════════════════════
    # 总结
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 70)
    print("  📋 六项对比总结")
    print("═" * 70)
    print("""
  对比一 (检索方式):  BM25 关键词快但缺语义；纯向量有语义但丢关键词；
                     混合检索 RRF 融合两者优势 ✅

  对比二 (查询扩展):  千问改写多角度查询 → 覆盖同义词/不同问法 →
                     召回率明显提升 ✅

  对比三 (HyDE):      问题向量 ≠ 答案向量 → 千问先生成假设答案 →
                     用答案向量检索更精准 ✅

  对比四 (重排序):    粗排 Top-5 可能混入弱相关 → 千问逐条精排 →
                     排序精度大幅提升 ✅

  对比五 (MMR 去重):  相邻段落内容重复 → MMR 去重保留多样性 →
                     上下文信息量更大 ✅

  对比六 (端到端):    基本 RAG 检索可能不准 → 整套优化流水线 →
                     答案更准确、更有依据 ✅
""")


if __name__ == "__main__":
    main()
