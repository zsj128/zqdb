# -*- coding: utf-8 -*-
"""
混合检索模块：从 main.py 拆出。

实现 Jieba 关键词命中 + 向量语义 + RRF 融合排序。
依赖全局状态（collection / chunks / jieba_tokens）通过 set_index() 注入，
由 main.py 在知识库加载/刷新后调用，避免模块间循环依赖。
"""
import jieba
from config import STOP_WORDS
from data_input import search_chunks


# ============================================================
# 模块级索引状态（由 main 注入）
# ============================================================
collection = None
chunks = []
jieba_tokens = []


def set_index(coll, chs, tokens):
    """注入当前活跃用户的知识库索引（collection + chunks + jieba 分词）。"""
    global collection, chunks, jieba_tokens
    collection = coll
    chunks = chs
    jieba_tokens = tokens


def get_index_state():
    return {
        "collection": collection,
        "chunks": chunks,
        "jieba_tokens": jieba_tokens,
        "count": collection.count() if collection else 0,
    }


def _vector_results(query):
    """向量语义检索（复用 data_input.search_chunks），转成 RRF 需要的格式。"""
    if not collection:
        return []
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
    return vec_results


def _jieba_results(query):
    """Jieba 关键词命中计数排序。"""
    q_token_set = set(t for t in jieba.cut(query, cut_all=True)
                      if t.strip() and len(t) >= 1 and t not in STOP_WORDS)
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
                              "source_file": c.get('source_file', ''),
                              "source_type": c.get('source_type', ''),
                              "article_key": c.get('article_key', ''),
                              "article_content": c.get('article_content', '')})
    return jieba_results


def hybrid_search(query, n_results=5, source_type: str = ""):
    """Jieba关键词命中 + 向量语义 + RRF融合排序; source_type 可选 'law'/'sample'"""
    if not jieba_tokens or not collection:
        return []

    vec_results = _vector_results(query)
    jieba_results = _jieba_results(query)

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
