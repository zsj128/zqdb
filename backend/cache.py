# -*- coding: utf-8 -*-
"""
问答语义缓存模块（参考 day62，升级为语义相似度命中）：
  - 精确字符串命中（完全相同问题）
  - 语义相似度命中（问题语义相近，如"盗窃罪怎么判刑" 与 "盗窃罪如何量刑"）
缓存每条记录：问题 + 问题向量 + 答案 + 模型。

命中阈值 sim_threshold 需谨慎设置：
  - 过低（如 0.85）会把"盗窃罪2000元怎么判刑"误命为"盗窃罪怎么判刑"，回答无针对性
  - 0.92 是实测较合理的值：命中等价表述，拦截需要针对性回答的问题
"""
import hashlib
import time


class AnswerCache:
    def __init__(self, max_size: int = 256, ttl: int = 1800,
                 sim_threshold: float = 0.92):
        self._d = {}           # key -> {question, vec, ans, ts, model, ctx}
        self._order = []
        self.max_size = max_size
        self.ttl = ttl
        self.sim_threshold = sim_threshold   # 语义相似度命中阈值
        self.embed_fn = None   # 由 init_chroma 注入向量化函数

    def _exact_key(self, question, model):
        return hashlib.md5(f"{question}|{model}".encode("utf-8")).hexdigest()

    @staticmethod
    def _cosine(a, b):
        """余弦相似度，值域 [-1,1]，越大越相似。"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _get_vector(self, text):
        """用嵌入模型生成向量；失败返回 None（则退回纯精确匹配）。"""
        fn = self.embed_fn
        if fn is None:
            return None
        try:
            vec = fn([text])[0]
            if hasattr(vec, 'tolist'):
                vec = vec.tolist()
            return vec
        except Exception:
            return None

    def get(self, question, context, model):
        """命中且未过期则返回答案，否则返回 None。

        命中策略：
          1. 先精确匹配问题+模型（快速路径）
          2. 未命中且能向量化：遍历缓存找语义最相近且未过期的问题，
             相似度 >= 阈值 则视为命中（复用该答案）
        """
        now = time.time()
        # 过期清理
        expired = [k for k, v in self._d.items() if v['ts'] < now]
        for k in expired:
            self._d.pop(k, None)
            if k in self._order:
                self._order.remove(k)

        # 1. 精确匹配
        exact = self._exact_key(question, model)
        if exact in self._d:
            self._refresh(exact)
            return self._d[exact]['ans']

        # 2. 语义匹配：问题向量与缓存中问题向量比较
        qvec = self._get_vector(question)
        if qvec is None or not self._d:
            return None
        best_k, best_sim = None, 0.0
        for k, entry in self._d.items():
            if entry.get('vec') is None:
                continue
            sim = self._cosine(qvec, entry['vec'])
            if sim > best_sim:
                best_sim, best_k = sim, k
        if best_k is not None and best_sim >= self.sim_threshold:
            self._refresh(best_k)
            return self._d[best_k]['ans']
        return None

    def _refresh(self, k):
        """命中后刷新 LRU 顺序。"""
        if k in self._order:
            self._order.remove(k)
        self._order.append(k)

    def set(self, question, context, model, answer):
        k = self._exact_key(question, model)
        vec = self._get_vector(question)
        self._d[k] = {
            'question': question, 'vec': vec, 'ans': answer,
            'ts': time.time() + self.ttl, 'model': model, 'ctx': context,
        }
        self._refresh(k)
        # 超容淘汰最久未用
        while len(self._order) > self.max_size:
            old = self._order.pop(0)
            self._d.pop(old, None)
