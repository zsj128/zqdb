import re
import os
import fitz  
import docx


def read_pdf(pdf_path):
    """读取 PDF 文本内容（统一提取，不做格式依赖的特殊清洗）"""
    doc = fitz.open(pdf_path)
    text = ''
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def read_docx(docx_path):
    """使用 python-docx 读取 docx 文件内容"""
    doc = docx.Document(docx_path)
    text = ''.join([i.text for i in doc.paragraphs])
    return text


def read_file(file_path, source_type="law"):
    """通用读取：根据扩展名读取 PDF 或 Word (.docx)，并做统一清洗。

    - law（法律）: 去除固定水印、页码、章节标题与多余空白，统一为规整文本。
    - sample（案例）: 去除固定水印、页码与多余空白，保留完整内容。
    PDF 与 .docx 两种格式共用同一套后处理逻辑。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        raw = read_pdf(file_path)
    elif ext in ('.docx', '.doc'):
        raw = read_docx(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

    # 统一清洗：去水印 -> 去页码 -> 去多余空白
    text = raw
    if source_type == "law":
        # 法律文档：先剥离“第X章/第X节”等章节标题及“第一条”之前的说明性文字
        text = raw.replace('人民法院案例库', '')
        text = re.sub(
            r'第[一二三四五六七八九十百千万零]+[章节][^第]*?(?=第[一二三四五六七八九十百千万零]+条)',
            '',
            text
        )
        text = re.sub(r'^.*?(?=第一条)', '', text, count=1)
    # 两类文档都要清除水印、页码与连续空白
    text = text.replace('人民法院案例库', '')
    # 清除页码：兼容半角/全角数字，如 "—５７１—"、" - 5 - "、"第3页"、"Page 5"
    # 注意：PDF 页码可能逐字符换行（"—\n０\n１\n—"），因此允许数字间含空白
    text = re.sub(r'第\s*[0-9０-９]+\s*页|Page\s*[0-9０-９]+', ' ', text)
    text = re.sub(r'[-–—－]{1,2}\s*(?:[0-9０-９]\s*){1,4}[-–—－]{1,2}', '', text)
    text = re.sub(r'\s+', '', text)                            # 所有连续空白符
    return text.strip()


def read_txt_file(file_path):
    """读取纯文本 / Markdown 文件（.txt / .md）"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def parse_attachment(file_path, max_chars=8000):
    """解析用户在问答中上传的附件，返回纯文本内容（作为单次对话上下文，不写入知识库）。

    支持格式：.pdf / .docx / .doc / .md / .txt
    返回前截断到 max_chars 字符，避免超出模型 token 限制。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        text = read_pdf(file_path)
    elif ext in ('.docx', '.doc'):
        text = read_docx(file_path)
    elif ext in ('.md', '.txt'):
        text = read_txt_file(file_path)
    else:
        raise ValueError(f"不支持的附件格式: {ext}")

    text = text.replace('人民法院案例库', '')
    text = re.sub(r'\s+', '', text)          # 压缩连续空白，节省 token
    return text[:max_chars]


def chunk_document(file_path, source_type="law"):
    """分块文档：
    - law（法律）: 按'第X条'边界精确分割，支持 .docx/.pdf
    - sample（案例）: 按段落/固定长度分割，保留完整内容
    """
    basename = os.path.basename(file_path)

    # 统一读取 PDF / Word（.docx/.doc），内部按 source_type 完成一致的后处理
    full_text = read_file(file_path, source_type=source_type)

    # ===== 案例文档：保留完整内容的段落分块 =====
    if source_type == "sample":
        return _chunk_case(basename, full_text)

    # ===== 法律文档：按 第X条 精确分割 =====
    law_name = basename.split('_')[0]

    protected_refs = []
    def _protect_ref(m):
        protected_refs.append(m.group(0))
        return f'\x00REF{len(protected_refs) - 1}\x00'
    #考虑"依照本法第三十九条、第四十条的规定..."的情况，

    # 条文标题模式：支持 "第二百六十四条" 及 "第二百六十二条之二"、"第二百一十条之一" 等
    ARTICLE_RE = r'第[一二三四五六七八九十百千万零\d]+条(?:之[一二三四五六七八九十]+)?'
    # 保护"本法第X条第Y款"这类组合引用，避免误切分
    full_text = re.sub(
        r'本法第[一二三四五六七八九十百千万零\d]+条(?:第[一二三四五六七八九十百千万零\d]+[款项])?(?:、[一二三四五六七八九十百千万零\d]+[款项])*',
        _protect_ref, full_text)
    full_text = re.sub(r'(?:和|或|及|，|；)(?:依照)?第[一二三四五六七八九十百千万零\d]+条',
                       _protect_ref, full_text)

    parts = re.split(f'({ARTICLE_RE})', full_text)
    articles_dict = {}
    j = 0
    while j < len(parts):
        if re.match(f'^{ARTICLE_RE}$', parts[j]):
            header = parts[j]
            body = ''
            k = j + 1
            while k < len(parts) and not re.match(f'^{ARTICLE_RE}$', parts[k]):
                body += parts[k]
                k += 1
            body = body.strip()
            for idx, ref in enumerate(protected_refs):
                body = body.replace(f'\x00REF{idx}\x00', ref)
            if len(body) > 5:
                articles_dict[f"{law_name}{header}"] = body
            j = k
        else:
            j += 1

    chunks = []
    for ak, body in articles_dict.items():
        chunks.append({'text': f"{ak}：{body}", 'chunk_id': f'chunk_{len(chunks) + 1}', 
                       'article_key': ak, 'article_content': body})
    print(f"[法律] 共提取 {len(chunks)} 个条文")
    return chunks


def _chunk_case(filename, text):
    """案例分块：整篇作为一个chunk"""
    case_title = re.sub(r'\.(pdf|docx)$', '', filename)
    
    chunk = {
        'text': f"【案例】{case_title}{text}",
        'chunk_id': '',
        'article_key': case_title,
        'article_content': text,
    }
    
    print(f"[案例] {case_title} → 1 个分块")
    return [chunk]

def search_chunks(collection, query, n_results=5):
    results = collection.query(
        query_texts=[query], n_results=n_results,
        include=['documents', 'metadatas', 'distances']
    )
    formatted = []
    for i in range(len(results['ids'][0])):
        m = results['metadatas'][0][i]
        formatted.append({
            "chunk_id": results['ids'][0][i],  # ChromaDB 原始 ID，用于 RRF 去重
            "text": results['documents'][0][i],
            "similarity": round(1 - results['distances'][0][i], 4),
            "char_count": m.get('char_count', 0),
            "articles": m.get('articles', ''),
            "source_file": m.get('source_file', ''),
            "source_type": m.get('source_type', ''),
            "article_key": m.get('article_key', ''),
            "article_content": m.get('article_content', ''),
        })
    return formatted


def display_results(results, title="搜索结果"):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")
    for i, item in enumerate(results, 1):
        if item.get('similarity')>0.4:
            arts = item.get('articles', '')
            label = f"【条文: {arts}】" if arts else ""
            print(f"\n--- 结果 {i} {label} ---")
            print(f"  页码: {item.get('page')} | 相似度: {item.get('similarity')} | 长度: {item.get('char_count')}字")
            print(f"  {'─' * 50}")
            print(item['text'])
            print(f"  {'─' * 50}")