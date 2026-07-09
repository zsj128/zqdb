import re
import fitz  # PyMuPDF
import docx

def read_pdf(pdf_path):
    """读取 PDF 并去除固定水印'人民法院案例库'"""
    doc = fitz.open(pdf_path)
    text = ''
    for page in doc:
        text += page.get_text()
    doc.close()
    text = text.replace('人民法院案例库', '')
    text = re.sub(r'第\s*\d+\s*页|Page\s*\d+', ' ', text)
    return text


def clean_text(text):
    """清洗文本：去页码、去多余空白（docx 用，无水印）"""
    text = re.sub(r'第\s*\d+\s*页|Page\s*\d+', ' ', text)#清除页码标记
    text = re.sub(r'[-–—－]{1,2}\s*\d+\s*[-–—－]{1,2}', '', text)#清除如 - 5 -、—12—
    text = re.sub(r'\s+', '', text)#清除所有连续空白符（空格、换行、制表符等）
    return text.strip()


def read_docx(docx_path):
    """使用 python-docx 读取 docx 文件内容"""
    doc = docx.Document(docx_path)
    text = ''.join([i.text for i in doc.paragraphs])
    text_cleaned_1=re.sub(
        r'第[一二三四五六七八九十百零]+[章节][^第]*?(?=第[一二三四五六七八九十百零]+条)', 
        '', 
        text
    )

    text_cleaned_2=re.sub(r'^.*?(?=第一条)', '', text_cleaned_1, count=1)
    return text_cleaned_2


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
    law_name = basename.split('_')[0]

    protected_refs = []
    def _protect_ref(m):
        protected_refs.append(m.group(0))
        return f'\x00REF{len(protected_refs) - 1}\x00'
    #考虑"依照本法第三十九条、第四十条的规定..."的情况，

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