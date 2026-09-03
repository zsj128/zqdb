# -*- coding: utf-8 -*-
"""
知识库存储模块：从 main.py 拆出。

负责 ChromaDB 按用户隔离的持久化目录管理 + 法律/案例文件导入。
每个用户在 chroma_kb/ 下有独立目录 user{id}_{用户名}/，内部使用固定集合名 legal_kb。

依赖注入：
  - embed_fn / embed_fn_setter  嵌入函数（由 main.init_chroma 注入）
  - reset_callback              重置时通知 main 清空检索索引
  - refresh_callback            导入后通知 main 重建检索索引
  - get_embed_fn                供外部读取当前嵌入函数
"""
import os
import re
import shutil
from urllib.parse import quote
import chromadb
from config import CHROMA_PATH, DATA_DIR, KB_COLLECTION_NAME, STOP_WORDS
from data_input import chunk_document
from database import get_username_by_id, get_user_imports, delete_user_imports
import retrieval   # 检索索引（chunks / jieba_tokens）由 retrieval 模块持有


# ============================================================
# 模块级共享状态
# ============================================================
_embedding_fn = None
_user_name_cache = {}   # user_id -> username，避免频繁查库
_user_clients = {}      # "user{id}_{name}" -> PersistentClient
_current_client = None  # 当前活跃用户的 client
collection = None       # 当前活跃用户的集合
current_user_id = 0
current_username = ""


def configure(embed_fn):
    """注入嵌入函数（在 app startup 时调用）。"""
    global _embedding_fn
    _embedding_fn = embed_fn


def get_embed_fn():
    return _embedding_fn


def is_kb_collection(name):
    """判断某集合是否属于本项目的知识库集合（兼容旧命名与新命名）"""
    return name == KB_COLLECTION_NAME or name.startswith('pdf_knowledge_base_v3') or name.startswith('user')


# ============================================================
# 用户目录 / client 管理
# ============================================================

def _username_safe(username):
    """将用户名编码为目录名合法的字符（仅保留字母数字 _-，其余做 url 编码）"""
    if not username:
        return ""
    cleaned = re.sub(r'[^A-Za-z0-9_-]', '', username)
    if cleaned:
        return cleaned
    return quote(username, safe='')


def _user_dir_name(user_id, username=""):
    """生成每个用户独立的持久化目录名（user{id}_{用户名}）"""
    user_id = int(user_id)
    uname = username or _user_name_cache.get(user_id, "")
    safe = _username_safe(uname)
    if safe:
        return f"user{user_id}_{safe}"
    return f"user{user_id}"


def _get_user_client(user_id, username=""):
    """获取（或创建）某用户的独立 ChromaDB client，并设置其为当前活跃 client。

    每个用户在 chroma_kb 下拥有独立目录：chroma_kb/user{id}_{用户名}/
    """
    global _current_client, current_user_id, current_username
    dir_name = _user_dir_name(user_id, username)
    client = _user_clients.get(dir_name)
    if client is None:
        user_path = os.path.join(CHROMA_PATH, dir_name)
        os.makedirs(user_path, exist_ok=True)
        client = chromadb.PersistentClient(path=user_path)
        _user_clients[dir_name] = client
        print(f"📁 已为用户 {user_id}({username or '?'}) 建立独立知识库目录: {dir_name}")
    _current_client = client
    return client


def _resolve_username(user_id):
    """获取用户名（优先缓存，未命中则查库并缓存）"""
    user_id = int(user_id)
    if user_id in _user_name_cache:
        return _user_name_cache[user_id]
    uname = get_username_by_id(user_id)
    _user_name_cache[user_id] = uname
    return uname


def _cleanup_legacy_shared_kb():
    """一次性清理旧的共享知识库（旧结构：chroma_kb/chroma.sqlite3 + UUID 索引目录）。

    仅删除非用户独立目录的内容（即不属于 user{id}_{名}/ 的旧共享文件）。
    返回删除的条目数。
    """
    removed = 0
    if not os.path.isdir(CHROMA_PATH):
        return 0
    for item in os.listdir(CHROMA_PATH):
        full = os.path.join(CHROMA_PATH, item)
        if item == 'chroma.sqlite3':
            try:
                os.remove(full)
                removed += 1
            except Exception:
                pass
        elif os.path.isdir(full) and not item.startswith('user'):
            try:
                shutil.rmtree(full, ignore_errors=True)
                removed += 1
            except Exception:
                pass
    return removed


# ============================================================
# 初始化 / 用户加载 / 重置
# ============================================================

def init_chroma():
    """初始化 ChromaDB 目录与旧数据清理（不创建嵌入模型）。

    嵌入模型由 main.py 创建后通过 configure() 注入。
    """
    global _current_client, current_user_id, current_username
    # 一次性清理旧共享库文件（保留用户独立目录）
    n = _cleanup_legacy_shared_kb()
    if n:
        print(f"🗑️ 清空重建：已清理 {n} 个旧共享知识库文件，将按「用户独立目录」重新隔离存储")
    else:
        print("🗑️ 旧共享知识库已清理或无需清理")

    _current_client = None
    current_user_id = 0
    current_username = ""
    print("ChromaDB 已就绪：每个用户将拥有独立的 user{id}_{用户名}/ 知识库目录")


def get_active_state():
    """返回当前活跃用户的实时知识库状态（供路由层读取，避免启动时的快照失效）"""
    return {
        "collection": collection,
        "chunks": retrieval.chunks,
        "jieba_tokens": retrieval.jieba_tokens,
        "count": collection.count() if collection else 0,
        "username": current_username,
    }


def ensure_user_loaded(user_id):
    """确保当前全局集合绑定到指定用户。

    每个用户在 chroma_kb 下有独立目录 user{id}_{用户名}/，使用该用户的独立 client。
    返回 {count, username} 该用户当前的数据条数。
    """
    global collection, current_user_id, current_username, _current_client
    if not _embedding_fn:
        raise RuntimeError("ChromaDB 尚未初始化")
    user_id = int(user_id)
    username = _resolve_username(user_id)
    if collection is not None and current_user_id == user_id:
        return {"count": collection.count(), "username": username}
    # 获取/创建该用户独立的 client（切换活跃 client）
    client = _get_user_client(user_id, username)
    collection = client.get_or_create_collection(
        name=KB_COLLECTION_NAME,
        metadata={
            "description": f"法律知识库(user{user_id}:{username})",
            "username": username,
            "user_id": str(user_id),
            "hnsw:space": "cosine",
        },
        embedding_function=_embedding_fn,
    )
    current_user_id = user_id
    current_username = username
    _current_client = client
    _refresh_index()
    print(f"👤 已加载用户 {user_id}({username}) 的知识库: {collection.count()} 条")
    return {"count": collection.count(), "username": username}


def reset_all_kb():
    """清空所有用户知识库（彻底重建），返回删除的集合数量。"""
    global collection, current_user_id, current_username, _current_client
    removed = 0
    if _current_client is not None:
        try:
            for c in _current_client.list_collections():
                name = c.name if hasattr(c, 'name') else str(c)
                if is_kb_collection(name):
                    try:
                        _current_client.delete_collection(name)
                        removed += 1
                    except Exception:
                        pass
        except Exception:
            pass
    collection = None
    current_user_id = 0
    current_username = ""
    _current_client = None
    _user_clients.clear()
    _user_name_cache.clear()
    retrieval.set_index(None, [], [])   # 清空检索索引
    return removed


def delete_user_data(user_id):
    """删除指定用户的本地数据（知识库向量目录 + 上传文件目录）。

    - 删除 chroma_kb/user{id}_{用户名}/ 整个目录
    - 删除 data/upload/{user_id}/ 整个目录
    - 若该用户当前是活跃用户，重置内存中的 collection / 索引状态
    返回 {"kb_dir_removed": bool, "upload_dir_removed": bool}
    """
    global collection, current_user_id, current_username, _current_client
    user_id = int(user_id)
    username = _resolve_username(user_id)

    # 1. 先通过 ChromaDB client 正确删除 collection（释放 sqlite 连接），
    #    避免直接删目录后 ChromaDB 内存缓存/未关闭连接导致数据复活。
    kb_removed = False
    dir_name = _user_dir_name(user_id, username)
    client = _user_clients.get(dir_name)
    if client is None and _current_client is not None and current_user_id == user_id:
        client = _current_client
    if client is not None:
        try:
            client.delete_collection(name=KB_COLLECTION_NAME)
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass

    # 2. 删除知识库目录（含历史遗留的大小写不一致目录，全部匹配前缀 user{id}_）
    if os.path.isdir(CHROMA_PATH):
        for item in os.listdir(CHROMA_PATH):
            full = os.path.join(CHROMA_PATH, item)
            if os.path.isdir(full) and item.startswith(f"user{user_id}_"):
                shutil.rmtree(full, ignore_errors=True)
                kb_removed = True

    # 3. 删除上传文件目录 data/upload/{user_id}/
    upload_removed = False
    upload_dir = os.path.join(DATA_DIR, 'upload', str(user_id))
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)
        upload_removed = True

    # 4. 删除 MySQL 中该用户的导入记录（避免 reload 时按残留路径重新导入）
    imports_removed = 0
    try:
        r = delete_user_imports(user_id)
        imports_removed = r.get("removed", 0)
    except Exception:
        pass

    # 5. 清理内存中的 client 缓存与用户名校验缓存
    for key in [k for k in _user_clients if k.startswith(f"user{user_id}_") or k == f"user{user_id}"]:
        _user_clients.pop(key, None)
    _user_name_cache.pop(user_id, None)

    # 6. 若删除的正是当前活跃用户，重置全局集合与检索索引
    if current_user_id == user_id:
        collection = None
        current_user_id = 0
        current_username = ""
        _current_client = None
        retrieval.set_index(None, [], [])

    print(f"🗑️ 已删除用户 {user_id}({username}) 的本地数据：知识库目录={kb_removed}，上传目录={upload_removed}，导入记录={imports_removed}")
    return {"kb_dir_removed": kb_removed, "upload_dir_removed": upload_removed,
            "imports_removed": imports_removed}


# ============================================================
# 索引构建（Jieba 分词 + 同步到检索模块）
# ============================================================

def _build_jieba_tokens(chunks):
    """根据 chunks 构建 Jieba 分词索引。"""
    import jieba
    return [set(t for t in jieba.cut(c["text"])
                if t.strip() and len(t) >= 1 and t not in STOP_WORDS)
            for c in chunks]


def _refresh_index():
    """从当前 collection 重新构建 chunks + Jieba 分词索引，并同步到检索模块。"""
    global collection
    if not collection or collection.count() == 0:
        retrieval.set_index(None, [], [])
        return
    all_data = collection.get(include=['documents', 'metadatas'])
    chunks = [{"id": all_data['ids'][i], "text": all_data['documents'][i], **all_data['metadatas'][i]}
              for i in range(len(all_data['ids']))]
    tokens = _build_jieba_tokens(chunks)
    retrieval.set_index(collection, chunks, tokens)
    print(f"索引已刷新: {len(chunks)} 条数据")


def _get_imported():
    if not collection or collection.count() == 0:
        return set()
    return {m.get('source_file', '') for m in collection.get(include=['metadatas'])['metadatas'] if m.get('source_file')}


def has_imported_file(user_id, filename):
    """判断指定用户的知识库中是否已存在某个文件（按原始文件名精确匹配）。

    用于在上传落盘（改名去重）之前判断同名文件是否已导入，避免重复入库。
    """
    ensure_user_loaded(user_id)
    return os.path.basename(filename) in _get_imported()


# ============================================================
# 知识库文件列表
# ============================================================

def list_user_kb_files(user_id):
    """返回当前用户知识库中实际已加载的所有文件（从该用户集合的元数据聚合）。

    按 source_file 聚合，统计每个文件加载的 chunk 数量与来源类型。
    返回: {"total_files": N, "total_chunks": M, "files": [{"filename", "source_type", "chunks"}]}
    """
    global collection, current_user_id
    if not _embedding_fn:
        return {"total_files": 0, "total_chunks": 0, "files": []}
    # 绑定该用户集合（若已绑定则直接使用，否则加载）
    if collection is None or current_user_id != int(user_id):
        ensure_user_loaded(user_id)
    if not collection or collection.count() == 0:
        return {"total_files": 0, "total_chunks": 0, "files": []}

    all_data = collection.get(include=['metadatas'])
    metas = all_data.get('metadatas') or []
    stat = {}
    for m in metas:
        sf = m.get('source_file', '')
        st = m.get('source_type', '')
        if not sf:
            continue
        key = (sf, st)
        stat[key] = stat.get(key, 0) + 1

    files = [
        {"filename": sf, "source_type": st, "chunks": cnt}
        for (sf, st), cnt in sorted(stat.items())
    ]
    return {
        "total_files": len(files),
        "total_chunks": sum(cnt for cnt in stat.values()),
        "files": files,
    }


# ============================================================
# 文件导入
# ============================================================

def _import_one(pdf_path, source_type):
    """解析单个文件并入库（写入当前用户集合）。

    使用 upsert 写入（幂等：重复导入同文件会覆盖而非报错），
    并统一收集到一批后由 collection.add 一次性批量 embedding。
    """
    global collection, current_user_id
    filename = os.path.basename(pdf_path)
    print(f"  📄 解析 [{source_type}] {filename} ...")
    raw = chunk_document(pdf_path, source_type=source_type)
    total = 0
    for start in range(0, len(raw), 500):
        batch = raw[start:start + 500]
        docs = [c['text'] for c in batch]
        ids = [f"{source_type}_u{current_user_id}_{filename}_{start+i}" for i in range(len(batch))]
        metas = [{
            "char_count": len(c['text']), "source_type": source_type, "source_file": filename,
            "article_key": c.get('article_key', ''),
            "article_content": c.get('article_content', ''),
        } for c in batch]
        try:
            collection.upsert(documents=docs, metadatas=metas, ids=ids)
        except Exception:
            for j in range(len(batch)):
                try:
                    collection.upsert(documents=[docs[j]], metadatas=[metas[j]], ids=[ids[j]])
                except Exception:
                    pass
        total += len(batch)
    print(f"  ✅ {filename} → {total} 条已入库")
    return total


def import_files(file_paths, source_type):
    """批量导入多个文件：所有文件入库完成后，仅重建一次检索索引。

    相比逐个调用 import_file（每文件各重建一次索引），大幅减少
    全量 collection.get + jieba 分词的开销。适用于文件夹多文件导入。

    返回 {"count": 成功文件数, "chunks": 成功入库条数, "skipped": 已存在跳过数,
          "errors": [{"file","error"}]}
    """
    imported = _get_imported()
    count = 0
    chunks = 0
    skipped = 0
    errors = []
    for fp in file_paths:
        name = os.path.basename(fp)
        if not name.lower().endswith(('.pdf', '.docx')):
            errors.append({"file": name, "error": "不支持的文件格式，仅支持 pdf/docx"})
            continue
        if name in imported:
            skipped += 1
            print(f"  ⏭️ {name} — 已导入，跳过")
            continue
        try:
            n = _import_one(fp, source_type)
            chunks += n
            count += 1
        except Exception as e:
            errors.append({"file": name, "error": str(e)})
    if chunks > 0:
        _refresh_index()
    return {"count": count, "chunks": chunks, "skipped": skipped,
            "errors": errors, "files": len(file_paths)}


def import_folder(folder_path, source_type):
    """导入服务器上一整个目录的 .pdf/.docx 文件到知识库。

    返回 {"count": 成功导入文件数, "skipped": 已存在跳过数, "errors": [失败文件] }
    """
    folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"目录不存在: {folder_path}")

    imported = _get_imported()
    files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(('.pdf', '.docx'))
    ])
    count = 0
    skipped = 0
    errors = []
    for fp in files:
        name = os.path.basename(fp)
        if name in imported:
            skipped += 1
            print(f"  ⏭️ {name} — 已导入，跳过")
            continue
        try:
            count += _import_one(fp, source_type)
        except Exception as e:
            errors.append({"file": name, "error": str(e)})
    if count > 0:
        _refresh_index()
    return {"count": count, "skipped": skipped, "errors": errors, "files": len(files)}


def import_file(file_path, source_type):
    """导入服务器上的单个 .pdf/.docx 文件到知识库。"""
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    name = os.path.basename(file_path)
    if not name.lower().endswith(('.pdf', '.docx')):
        raise ValueError(f"不支持的文件格式: {name}，仅支持 pdf/docx")
    if name in _get_imported():
        return {"count": 0, "skipped": 1, "errors": [], "files": 1, "already": True}
    count = _import_one(file_path, source_type)
    if count > 0:
        _refresh_index()
    return {"count": count, "skipped": 0, "errors": [], "files": 1, "already": False}


def import_user_paths(user_id, source_type=""):
    """按用户从 MySQL 中读取已保存的目录/文件路径，全部(重新)导入。

    用于用户登录后自动恢复此前插入的数据。
    返回 {"folder_count":.., "file_count":.., "imported_files":.., "errors":[]}
    """
    records = get_user_imports(user_id, source_type=source_type)
    folder_count = file_count = imported_files = 0
    errors = []
    for rec in records:
        path = rec["path"]
        stype = rec["source_type"]
        try:
            if rec["kind"] == "folder":
                r = import_folder(path, stype)
                folder_count += 1
            else:
                r = import_file(path, stype)
                file_count += 1
            imported_files += (r.get("count") or 0)
            for e in (r.get("errors") or []):
                errors.append(e)
        except Exception as e:
            errors.append({"path": path, "error": str(e)})
    return {
        "folder_count": folder_count,
        "file_count": file_count,
        "imported_files": imported_files,
        "errors": errors,
    }
