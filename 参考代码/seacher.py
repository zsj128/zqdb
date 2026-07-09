from langchain_community.vectorstores import Chroma
from langchain.retrievers import EnsembleRetriever


with open("sample_data/test_docs.pkl", "rb") as f:
    docs = pickle.load(f)

# 1. 关键词检索器
bm25 = BM25Retriever.from_documents(docs, k=5)

# 2. 向量检索器
vs = Chroma.from_documents(docs, get_embeddings())
vs_retriever = vs.as_retriever(search_kwargs={"k": 5})

# 3. 混合检索器（权重各 50%）
ensemble = EnsembleRetriever(
    retrievers=[bm25, vs_retriever],
    weights=[0.5, 0.5],
)

# 4. 测试三种检索器
query = "向量数据库"
print(f"查询: '{query}'\n")

print("--- BM25 (关键词) ---")
for doc in bm25.invoke(query)[:3]:
    print(f"  {doc.page_content[:50]}...")

print("\n--- 向量检索 (语义) ---")
for doc in vs_retriever.invoke(query)[:3]:
    print(f"  {doc.page_content[:50]}...")

print("\n--- 混合检索 (Ensemble) ---")
for doc in ensemble.invoke(query)[:3]:
    print(f"  {doc.page_content[:50]}...")