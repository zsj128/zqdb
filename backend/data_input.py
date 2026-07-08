import re
import fitz  # PyMuPDF
import docx


def _is_watermark_span(span: dict)->bool:
    """判断一个 span 是否为斜向水印（对象级检测）
    
    斜向水印特征（用户确认：可选中、可复制、斜着放的单字）:
    1. flags bit0=1 (斜体) + 字体较大 → 水印
    2. 文字是重复字符 (如 库库库库) → 水印  
    3. 字体异常大 (>18pt) → 水印
    """
    size = span.get('size', 12)
    flags = span.get('flags', 0)
    text = span.get('text', '')
    
    # 特征1：斜体 + 大字体组合（最可靠的水印标识）
    if (flags & 1) and size > 10:
        return True
    
    # 特征2：纯重复文字（>=3个相同字符）
    if len(text) >= 3 and len(set(text)) == 1:
        return True
    
    # 特征3：字体异常大
    if size > 18:
        return True
    
    # 特征4：重复为主（如 "库库库库" 或 "法法法法"）
    if len(text) >= 4 and len(set(text)) <= 2 and len(text) / len(set(text)) >= 2.5:
        return True
    
    return False


def read_pdf(pdf_path):
    """PyMuPDF 方案：逐 span 检测并跳过斜向水印文本"""
    doc = fitz.open(pdf_path)
    all_text = []
    wm_skipped = 0
    
    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        
        page_lines = []
        for block in blocks:
            if block["type"] != 0:  # 非文本块
                continue
            
            for line in block.get("lines", []):
                normal_spans = []
                for span in line.get("spans", []):
                    if _is_watermark_span(span):
                        wm_skipped += len(span.get("text", ""))
                        continue
                    normal_spans.append(span.get("text", ""))
                
                if normal_spans:
                    page_lines.append("".join(normal_spans))
        
        if page_lines:
            raw = "".join(page_lines)
            raw = re.sub(r'第\s*\d+\s*页|Page\s*\d+', ' ', raw)
            raw = re.sub(r'[-–—－]{1,2}\s*\d+\s*[-–—－]{1,2}', '', raw)
            raw = re.sub(r'\s+', '', raw).strip()
            if raw:
                all_text.append(raw)
    
    doc.close()
    
    if wm_skipped > 0:
        print(f"  [去水印] 跳过 {wm_skipped} 个水印字符（对象级检测）")
    
    result = ''.join(all_text)
    
    # 兜底：正则清除漏网之鱼
    before_fb = len(result)
    result = re.sub(r'(.)\1{2,}', '', result)
    if len(result) < before_fb:
        print(f"  [兜底] 正则清理 {before_fb - len(result)} 个残留")
    
    return result


def clean_text(text):
    """清洗文本：去页码、去多余空白（docx 用，无水印）"""
    text = re.sub(r'第\s*\d+\s*页|Page\s*\d+', ' ', text)
    text = re.sub(r'[-–—－]{1,2}\s*\d+\s*[-–—－]{1,2}', '', text)
    text = re.sub(r'\s+', '', text)
    return text.strip()


def read_docx(docx_path):
    """使用 python-docx 读取 docx 文件内容"""
    doc = docx.Document(docx_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full_text = ''.join(paragraphs)
    return clean_text(full_text)


def chunk_document(file_path, source_type="law"):
    """分块文档：
    - law（法律）: 按'第X条'边界精确分割，支持 .docx/.pdf
    - sample（案例）: 按段落/固定长度分割，保留完整内容
    """
    import os
    basename = os.path.basename(file_path)

    # 根据文件扩展名选择读取方式
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.docx':
        full_text = read_docx(file_path)
    elif ext == '.pdf':
        full_text = read_pdf(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

    # ===== 案例文档：保留完整内容的段落分块 =====
    if source_type == "sample":
        return _chunk_case(basename, full_text)

    # ===== 法律文档：按 第X条 精确分割 =====
    law_name = re.sub(r'_\d{8}\.(docx|pdf)$|\.(docx|pdf)$', '', basename)
    full_text = re.sub(r'第[一二三四五六七八九十百零\d]+[章节][^第]{0,50}', '', full_text)

    protected_refs = []
    def _protect_ref(m):
        protected_refs.append(m.group(0))
        return f'\x00REF{len(protected_refs) - 1}\x00'

    full_text = re.sub(
        r'本法第[一二三四五六七八九十百零\d]+条(?:第[一二三四五六七八九十百零\d]+[款项])?(?:、[一二三四五六七八九十百零\d]+[款项])*',
        _protect_ref, full_text)
    full_text = re.sub(r'(?:和|或|及|，|；)(?:依照)?第[一二三四五六七八九十百零\d]+条',
                       _protect_ref, full_text)

    parts = re.split(r'(第[一二三四五六七八九十百零\d]+条)', full_text)
    articles_dict = {}
    j = 0
    while j < len(parts):
        if re.match(r'^第[一二三四五六七八九十百零\d]+条$', parts[j]):
            header = parts[j]
            body = ''
            k = j + 1
            while k < len(parts) and not re.match(r'^第[一二三四五六七八九十百零\d]+条$', parts[k]):
                body += parts[k]
                k += 1
            body = body.strip()
            for idx, ref in enumerate(protected_refs):
                body = body.replace(f'\x00REF{idx}\x00', ref)
            if len(body) > 10:
                articles_dict[f"{law_name}{header}"] = body
            j = k
        else:
            j += 1

    chunks = []
    for ak, body in articles_dict.items():
        chunks.append({'text': f"{ak}：{body}", 'page': '1', 'articles': ak,
                       'chunk_id': f'chunk_{len(chunks) + 1}', 'article_key': ak, 'article_content': body})
    print(f"[法律] 共提取 {len(chunks)} 个条文")
    return chunks


def _chunk_case(filename, text, max_len=1500):
    """案例分块：按固定长度切分，保留完整内容"""
    case_title = re.sub(r'\.(pdf|docx)$', '', filename)
    # 恢复换行用于分段
    text = re.sub(r'([。！？；])', r'\1\n', text)
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 5]

    chunks = []
    current = ''
    for para in paragraphs:
        if len(current) + len(para) > max_len and current:
            chunks.append(_make_case_chunk(case_title, current))
            current = para
        else:
            current = current + (' ' if current else '') + para
    if current:
        chunks.append(_make_case_chunk(case_title, current))

    print(f"[案例] {case_title} → {len(chunks)} 个分块")
    return chunks


def _make_case_chunk(title, content):
    return {
        'text': f"【案例】{title}\n{content}",
        'page': '1',
        'articles': title,
        'chunk_id': '',
        'article_key': title,
        'article_content': content,
    }


# 保持向后兼容
chunk_pdf = chunk_document


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
            "page": m.get('page', '?'),
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


