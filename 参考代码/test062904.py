import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import pdfplumber
import chromadb
from sentence_transformers import SentenceTransformer
import re


# ==========================================
#  将前5节课的所有函数整合到一个类中
# ==========================================

class PDFRAG:
    """基于 PDF 文档的 RAG 问答系统"""

    def __init__(self, db_path="./pdf_rag_db",
                 model_name='paraphrase-multilingual-MiniLM-L12-v2'):
        """
        初始化系统

        参数：
            db_path: Chroma 数据库的存储路径
            model_name: Sentence-BERT 模型名称
        """
        print("🚀 正在初始化 PDF-RAG 系统...")

        # 1. 加载向量化模型
        self.model = SentenceTransformer(model_name)
        print(f"   ✅ 模型已加载: {model_name}")

        # 2. 初始化 Chroma 客户端
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = None  # 稍后在 load_pdf() 中创建
        print(f"   ✅ Chroma 已连接: {db_path}")

        # 3. 配置参数
        self.chunk_size = 300
        self.overlap = 50
        self.max_context_chars = 3000

        print("   ✅ 系统就绪！\n")

    # ====== 第1课时：PDF 解析 ======

    @staticmethod
    def clean_pdf_text(text, page_num=None):
        """清洗 PDF 文本"""
        if not text:
            return ""
        text = re.sub(r'第\s*\d+\s*页', '', text)
        lines = text.split('\n')
        merged = []
        for line in lines:
            line = line.strip()
            if not line:
                merged.append('')
                continue
            if merged and merged[-1] and not merged[-1].endswith(
                    ('.', '。', '！', '？', '；', '：')
            ):
                merged[-1] += line
            else:
                merged.append(line)
        text = '\n'.join(merged)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # ====== 第2课时：文档分块 ======

    @staticmethod
    def smart_chunk(text, chunk_size=300, overlap=50):
        """智能分块"""
        sentences = re.split(r'(?<=[。！？\n])\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return []

        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= chunk_size:
                current += sentence
            else:
                if current:
                    chunks.append(current)
                current = current[-overlap:] + sentence if len(current) > overlap else sentence
        if current:
            chunks.append(current)
        return chunks

    # ====== 第3课时：向量化 + 存储 ======

    def load_pdf(self, pdf_path, collection_name="pdf_knowledge"):
        """
        加载 PDF 文件：解析 → 清洗 → 分块 → 向量化 → 存入 Chroma

        参数：
            pdf_path: PDF 文件路径
            collection_name: Collection 名称
        """
        print(f"📄 正在加载 PDF: {pdf_path}")

        # 1. 解析 PDF
        all_chunks = []
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"   共 {total_pages} 页")

            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                clean = self.clean_pdf_text(text, page_num=i + 1)
                if not clean:
                    continue

                chunks = self.smart_chunk(clean, self.chunk_size, self.overlap)
                for c_idx, chunk_text in enumerate(chunks):
                    all_chunks.append({
                        "text": chunk_text,
                        "page": i + 1,
                        "chunk_id": f"p{i + 1}_c{c_idx}",
                        "source": pdf_path
                    })

        print(f"   生成 {len(all_chunks)} 个文本块")

        # 2. 创建/获取 Collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # 3. 批量向量化并存入
        stored = 0
        batch_size = 500
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]

            # 向量化
            texts = [c['text'] for c in batch]
            embeddings = self.model.encode(texts).tolist()

            # 准备数据
            ids = [c['chunk_id'] for c in batch]
            metadatas = [{
                "page": c['page'],
                "chunk_id": c['chunk_id'],
                "source": c['source'],
                "char_count": len(c['text'])
            } for c in batch]

            self.collection.add(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            stored += len(batch)

        print(f"   ✅ 已存入 {stored} 块到向量数据库\n")
        return stored

    # ====== 第4课时：检索 ======

    def search(self, query, n_results=5):
        """语义检索"""
        if self.collection is None:
            raise ValueError("请先调用 load_pdf() 加载文档")

        # 向量化查询
        query_embedding = self.model.encode([query]).tolist()

        # 用向量检索（而不是 query_texts）
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results,
            include=['documents', 'metadatas', 'distances']
        )

        formatted = []
        if results['ids'][0]:
            for i in range(len(results['ids'][0])):
                distance = results['distances'][0][i]
                # similarity = 1 / (1 + distance)
                similarity = 1 - distance
                formatted.append({
                    "text": results['documents'][0][i],
                    "page": results['metadatas'][0][i].get('page', '?'),
                    "chunk_id": results['ids'][0][i],
                    "source": results['metadatas'][0][i].get('source', '?'),
                    "similarity": round(similarity, 4)
                })

        return formatted

    # ====== 第5课时：Prompt 构建 ======

    def build_prompt(self, query, search_results):
        """构建 RAG Prompt（优化溯源版本）"""
        context_parts = []
        total_chars = 0

        for i, r in enumerate(search_results):
            # 完整溯源：来源序号 + 文件 + 页码 + 块ID + 相似度
            source_info = f"【{i + 1}号参考片段】来源文件：{r['source']} | 第{r['page']}页 | 文本块ID：{r['chunk_id']} | 相关度 {r['similarity']:.2f}"
            chunk_text = r['text']
            if total_chars + len(chunk_text) > self.max_context_chars:
                remaining = self.max_context_chars - total_chars
                if remaining > 100:
                    chunk_text = chunk_text[:remaining] + "..."
                else:
                    break
            context_parts.append(f"{source_info}\n{chunk_text}")
            total_chars += len(chunk_text)

        context = "\n\n---\n\n".join(context_parts)

        # 重写强制规则，固定输出格式
        prompt = f"""你是一个基于文档内容回答问题的专业助手。
    ## 📋 硬性强制规则（必须严格遵守）
    1. 仅使用下方提供的文档片段作答，禁止编造不存在的内容；无相关信息直接回复「文档中未提及该问题相关内容」。
    2. 回答中引用信息时标注对应片段编号，**回答末尾必须单独一行输出完整溯源清单**，固定格式示例：
    引用溯源清单：
    [1] 文件：test_document.pdf，第2页，文本块ID：p2_c0
    [2] 文件：test_document.pdf，第5页，文本块ID：p5_c1
    3. 不允许只简写 [来源1]，必须完整写出文件、页码、块ID三者。
    4. 语言精炼准确，逻辑清晰；信息不足时明确说明。

    ## 📚 参考文档片段
    {context}

    ## ❓ 用户问题
    {query}

    ## ✅ 你的回答：
    """
        return prompt
#     def build_prompt(self, query, search_results):
#         """构建 RAG Prompt"""
#         context_parts = []
#         total_chars = 0
#
#         for i, r in enumerate(search_results):
#             source_info = f"[来源{i + 1}: {r['source']} 第{r['page']}页, "
#             source_info += f"相关度 {r['similarity']:.2f}]"
#
#             chunk_text = r['text']
#             if total_chars + len(chunk_text) > self.max_context_chars:
#                 remaining = self.max_context_chars - total_chars
#                 if remaining > 100:
#                     chunk_text = chunk_text[:remaining] + "..."
#                 else:
#                     break
#
#             context_parts.append(f"{source_info}\n{chunk_text}")
#             total_chars += len(chunk_text)
#
#         context = "\n\n---\n\n".join(context_parts)
#
#         prompt = f"""你是一个基于文档内容回答问题的专业助手。
#
# ## 📋 你的规则
# 1. **只基于下面提供的文档内容回答**。如果文档中没有相关信息，请诚实地说"文档中未提及"。
# 2. **引用来源**。回答时标注引用的文档来源编号，如 [来源1]、[来源2]。
# 3. **标注页码**。如果知道信息来自哪一页，请说出页码。
# 4. **保持简洁**。回答要准确、精炼，不要编造信息。
# 5. **如果不确定**。如果文档信息不足以给出确定答案，说明原因。
#
# ## 📚 相关文档内容
# {context}
#
# ## ❓ 用户问题
# {query}
#
# ## ✅ 请回答
# """
#         return prompt

    # ====== 综合：问答接口 ======

    def ask(self, query, api_key=None, model="qwen-turbo", n_results=5):
        """
        端到端问答：检索 → 构建Prompt → 调用LLM → 返回答案

        参数：
            query: 用户问题
            api_key: 大模型 API Key（可选，不提供则只看检索结果）
            model: 模型名称
            n_results: 检索返回的文档块数量
        """
        # Step 1: 检索
        print(f"🔍 检索: \"{query}\"")
        results = self.search(query, n_results=n_results)

        if not results:
            return {
                "answer": "抱歉，在文档中未找到相关信息。",
                "sources": [],
                "has_answer": False
            }

        print(f"   找到 {len(results)} 条相关结果")

        # Step 2: 构建 Prompt
        prompt = self.build_prompt(query, results)

        # Step 3: 如果有 API Key，调用大模型；否则只返回检索结果
        answer = None
        if api_key:
            print("🤖 调用大模型生成答案...")
            answer = self._call_llm(prompt, api_key, model)
        else:
            print("💡 (未提供 API Key，仅返回检索结果)")
            answer = self._format_results_only(results)

        return {
            "answer": answer,
            "sources": [
                {"page": r['page'], "similarity": r['similarity'],
                 "chunk_id": r['chunk_id'], "text_preview": r['text'][:100]}
                for r in results
            ],
            "has_answer": len(results) > 0,
            "prompt": prompt  # 调试用
        }

    def _call_llm(self, prompt, api_key, model):
        """调用大模型 API"""
        import requests

        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1000
        }

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"API 错误 ({response.status_code}): {response.text[:200]}"
        except Exception as e:
            return f"请求失败: {str(e)}"

    def _format_results_only(self, results):
        """没有 LLM 时，直接展示检索结果"""
        lines = ["（以下为检索到的相关文档内容，未经过大模型整合）\n"]
        for i, r in enumerate(results):
            lines.append(f"[来源{i + 1}] 第{r['page']}页 (相关度: {r['similarity']:.3f})")
            lines.append(r['text'][:200])
            lines.append("")
        return "\n".join(lines)


def interactive_qa(rag_system, api_key=None):
    """
    交互式问答界面

    命令：
        /help  - 显示帮助
        /quit  - 退出
        /load <path> - 加载新 PDF
        /stats - 查看统计
        直接输入问题 - 进行 RAG 问答
    """
    print("\n" + "=" * 60)
    print("  📚 PDF-RAG 问答系统")
    print("  输入 /help 查看命令，输入 /quit 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("\n💬 请输入问题 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        # 处理命令
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/quit" or cmd == "/q":
                print("👋 再见！")
                break
            elif cmd == "/help":
                print("""
命令列表:
  /help      - 显示此帮助
  /quit      - 退出系统
  /load PDF路径 - 加载新的 PDF 文件
  /stats     - 查看当前知识库统计
直接输入问题即可进行 RAG 问答
                """)
            elif cmd.startswith("/load "):
                path = user_input[6:].strip()
                try:
                    rag_system.load_pdf(path)
                    print(f"✅ 已加载: {path}")
                except Exception as e:
                    print(f"❌ 加载失败: {e}")
            elif cmd == "/stats":
                if rag_system.collection:
                    print(f"📊 知识库统计:")
                    print(f"   文档块总数: {rag_system.collection.count()}")
                else:
                    print("⚠️ 尚未加载任何文档")
            else:
                print(f"未知命令: {cmd}，输入 /help 查看帮助")
            continue

        # 进行问答
        result = rag_system.ask(user_input, api_key=api_key)
        print(f"\n{'=' * 60}")
        print(result['answer'])
        if result['sources']:
            print(f"\n📖 参考来源:")
            for idx, src in enumerate(result["sources"]):
                print(f"【{idx + 1}号片段】第{src['page']}页 | 块ID：{src['chunk_id']} | 相关度：{src['similarity']:.3f}")
            print("-" * 60)


if __name__ == "__main__":
    # 初始化
    rag = PDFRAG(db_path="D:/Code/python/test_document.pdf")

    # 加载 PDF
    rag.load_pdf("test_document.pdf")

    # 启动交互界面（可选 API Key）
    # 如果有通义千问 API Key，传入 api_key 参数即可启用 LLM 问答
    api_key = "sk-15bbae4de6c24d40b3ad116e6d7b3d20"  # 替换为你的 API Key: "sk-xxxxx"
    interactive_qa(rag, api_key=api_key)