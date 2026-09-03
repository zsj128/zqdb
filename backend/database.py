"""
用户数据库操作模块
基于 pymysql 连接 MySQL (zqdb_db)

数据库连接参数支持环境变量覆盖（便于 Docker 部署）：
  DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
未设置环境变量时使用默认值（本地开发）。
"""
import os
import pymysql

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "Aa@1233211234567"),
    "db": os.environ.get("DB_NAME", "zqdb_db"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def get_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def init_user_table():
    """初始化用户表 + 用户导入记录表（如果不存在）"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
                    password VARCHAR(128) NOT NULL COMMENT '密码',
                    email VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
                    phone VARCHAR(20) DEFAULT NULL COMMENT '手机号',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
            """)
            # 用户导入记录：保存用户通过网页插入的数据来源地址，下次登录自动恢复
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_imports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL COMMENT '所属用户',
                    source_type VARCHAR(20) NOT NULL COMMENT 'law=法律文件 | sample=法律案例',
                    kind VARCHAR(10) NOT NULL DEFAULT 'folder' COMMENT 'folder=目录 | file=单文件',
                    path VARCHAR(500) NOT NULL COMMENT '目录地址或文件路径',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    INDEX idx_user (user_id),
                    INDEX idx_user_type (user_id, source_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户导入记录表';
            """)
            # 用户 LLM 配置：每个用户绑定自己的 API Key / 模型
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_llm_config (
                    user_id INT PRIMARY KEY COMMENT '所属用户',
                    api_key VARCHAR(256) DEFAULT NULL COMMENT 'API Key',
                    model VARCHAR(100) DEFAULT NULL COMMENT '模型名称',
                    base_url VARCHAR(256) DEFAULT NULL COMMENT 'Base URL',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户LLM配置表';
            """)
        conn.commit()
        _ensure_admin_user(conn)
        print("✅ 用户表初始化完成")
    finally:
        conn.close()


# 管理员账号硬编码配置
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Aa@123456"


def _ensure_admin_user(conn):
    """在数据库初始化时创建硬编码管理员账号（幂等，已存在则忽略）。

    管理员账号只在用户表创建时写入，不参与普通注册流程。
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE username = %s", (ADMIN_USERNAME,)
            )
            if cursor.fetchone():
                return
            cursor.execute(
                "INSERT INTO users (username, password, email, phone) VALUES (%s, %s, %s, %s)",
                (ADMIN_USERNAME, ADMIN_PASSWORD, None, None)
            )
        conn.commit()
        print("👑 管理员账号 admin 已创建")
    except Exception as e:
        print(f"⚠️ 创建管理员账号失败: {e}")


def save_user_llm_config(user_id: int, api_key: str = "", model: str = "", base_url: str = "") -> dict:
    """保存某用户的 LLM 配置（UPSERT）"""
    if user_id <= 0:
        return {"success": False, "message": "无效的用户ID"}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_llm_config (user_id, api_key, model, base_url)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    api_key = VALUES(api_key),
                    model = VALUES(model),
                    base_url = VALUES(base_url)
            """, (user_id, api_key or None, model or None, base_url or None))
        conn.commit()
        return {"success": True, "message": "保存成功"}
    except Exception as e:
        return {"success": False, "message": f"保存失败: {str(e)}"}
    finally:
        conn.close()


def get_user_llm_config(user_id: int) -> dict:
    """读取某用户的 LLM 配置；无记录返回空字段"""
    if user_id <= 0:
        return {"api_key": "", "model": "", "base_url": ""}
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT api_key, model, base_url FROM user_llm_config WHERE user_id=%s",
                (user_id,)
            )
            row = cursor.fetchone()
        if not row:
            return {"api_key": "", "model": "", "base_url": ""}
        return {
            "api_key": row.get("api_key") or "",
            "model": row.get("model") or "",
            "base_url": row.get("base_url") or "",
        }
    except Exception:
        return {"api_key": "", "model": "", "base_url": ""}
    finally:
        conn.close()


def save_user_import(user_id: int, source_type: str, kind: str, path: str) -> dict:
    """记录用户插入的数据来源地址（目录或文件）"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 避免重复记录同一条目
            cursor.execute(
                "SELECT id FROM user_imports WHERE user_id=%s AND source_type=%s AND kind=%s AND path=%s",
                (user_id, source_type, kind, path)
            )
            if cursor.fetchone():
                return {"success": True, "message": "已记录", "saved": False}
            cursor.execute(
                "INSERT INTO user_imports (user_id, source_type, kind, path) VALUES (%s, %s, %s, %s)",
                (user_id, source_type, kind, path)
            )
        conn.commit()
        return {"success": True, "message": "记录成功", "saved": True}
    except Exception as e:
        return {"success": False, "message": f"记录失败: {str(e)}", "saved": False}
    finally:
        conn.close()


def get_user_imports(user_id: int, source_type: str = "") -> list:
    """读取某用户所有已保存的导入路径；可按 source_type 过滤"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if source_type:
                cursor.execute(
                    "SELECT id, source_type, kind, path, created_at FROM user_imports "
                    "WHERE user_id=%s AND source_type=%s ORDER BY created_at ASC",
                    (user_id, source_type)
                )
            else:
                cursor.execute(
                    "SELECT id, source_type, kind, path, created_at FROM user_imports "
                    "WHERE user_id=%s ORDER BY created_at ASC",
                    (user_id,)
                )
            return cursor.fetchall()
    except Exception:
        return []
    finally:
        conn.close()


def delete_user_imports(user_id: int) -> dict:
    """删除某用户的所有导入记录（清空本地数据时同步调用）。

    返回 {"success": bool, "removed": int}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_imports WHERE user_id = %s", (user_id,))
            removed = cursor.rowcount
        conn.commit()
        return {"success": True, "removed": removed}
    except Exception as e:
        return {"success": False, "removed": 0, "message": str(e)}
    finally:
        conn.close()


def register_user(username: str, password: str, email: str = "", phone: str = "") -> dict:
    """
    用户注册
    返回: {"success": bool, "message": str}
    """
    # 禁止注册与管理员同名的账号（管理员账号为系统保留）
    if username and username.strip().lower() == ADMIN_USERNAME:
        return {"success": False, "message": "该用户名为系统保留，无法注册"}

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查用户名是否已存在（数据库 UNIQUE 约束之外的应用层兜底判断）
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                return {"success": False, "message": "用户名已存在"}

            # 插入新用户（直接存储密码）
            cursor.execute(
                "INSERT INTO users (username, password, email, phone) VALUES (%s, %s, %s, %s)",
                (username, password, email or None, phone or None)
            )
        conn.commit()
        return {"success": True, "message": "注册成功"}
    except Exception as e:
        return {"success": False, "message": f"注册失败: {str(e)}"}
    finally:
        conn.close()


def get_username_by_id(user_id: int) -> str:
    """按用户 ID 查询用户名；找不到返回空字符串"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM users WHERE id=%s", (int(user_id),))
            row = cursor.fetchone()
            return (row or {}).get("username", "") or ""
    except Exception:
        return ""
    finally:
        conn.close()


def login_user(username: str, password: str) -> dict:
    """
    用户登录验证
    返回: {"success": bool, "message": str, "user_id": int|None, "username": str|None}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, password FROM users WHERE username = %s",
                (username,)
            )
            user = cursor.fetchone()

            if not user:
                return {"success": False, "message": "用户不存在", "user_id": None, "username": None}

            if user["password"] != password:
                return {"success": False, "message": "密码错误", "user_id": None, "username": None}

            is_admin = (user["username"].strip().lower() == ADMIN_USERNAME)
            return {
                "success": True,
                "message": "登录成功",
                "user_id": user["id"],
                "username": user["username"],
                "is_admin": is_admin
            }
    except Exception as e:
        return {"success": False, "message": f"登录失败: {str(e)}", "user_id": None, "username": None}
    finally:
        conn.close()


# ============================================================
# 管理员功能
# ============================================================

def is_admin_user(username: str) -> bool:
    """判断某用户名是否为管理员账号"""
    return bool(username) and username.strip().lower() == ADMIN_USERNAME


def _mask_api_key(key: str) -> str:
    """对 API Key 脱敏：保留前 3 位 + 后 4 位，中间用 * 遮蔽；过短则全遮蔽。"""
    if not key:
        return key
    if len(key) <= 8:
        return "*" * len(key)
    return key[:3] + "*" * (len(key) - 7) + key[-4:]


# 各表的主键字段名（用于管理员按主键删除单行数据）
_TABLE_PRIMARY_KEYS = {
    "users": "id",
    "user_imports": "id",
    "user_llm_config": "user_id",  # 该表无 id，主键为用户ID
}


def list_all_tables() -> dict:
    """管理员：查看 MySQL 数据库中所有表的所有数据。

    对 user_llm_config 表的 api_key 字段做脱敏（星号遮蔽），保护用户密钥安全。
    返回 {"success": bool, "tables": [{"name", "pk", "rows": [...]}]}
    其中 pk 为该表主键字段名，供前端"按主键删除单行"使用。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[list(row.keys())[0]] for row in cursor.fetchall()]
        result = []
        with conn.cursor() as cursor:
            for t in tables:
                try:
                    cursor.execute(f"SELECT * FROM `{t}`")
                    rows = cursor.fetchall()
                    # 对 api_key 字段脱敏
                    for row in rows:
                        if isinstance(row, dict) and "api_key" in row:
                            row["api_key"] = _mask_api_key(row["api_key"])
                    result.append({
                        "name": t,
                        "pk": _TABLE_PRIMARY_KEYS.get(t, "id"),
                        "rows": rows,
                    })
                except Exception as e:
                    result.append({"name": t, "pk": _TABLE_PRIMARY_KEYS.get(t, "id"),
                                   "rows": [], "error": str(e)})
        return {"success": True, "tables": result}
    except Exception as e:
        return {"success": False, "message": f"查询失败: {str(e)}"}
    finally:
        conn.close()


def delete_table_row(table: str, pk_value) -> dict:
    """管理员：删除指定表中主键值等于 pk_value 的那一行数据。

    table 必须是白名单内的表（users / user_imports / user_llm_config），
    防止 SQL 注入与越权删除。主键字段名由 _TABLE_PRIMARY_KEYS 决定。

    返回 {"success", "message", "affected": int}
    """
    if table not in _TABLE_PRIMARY_KEYS:
        return {"success": False, "message": f"不支持的表：{table}"}

    pk_field = _TABLE_PRIMARY_KEYS[table]

    # 保护：禁止通过此接口删除 admin 账号（users 表）
    if table == "users":
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT username FROM users WHERE id = %s", (pk_value,))
                row = cursor.fetchone()
            if row and is_admin_user(row.get("username", "")):
                return {"success": False, "message": "不能删除管理员账号"}
        except Exception as e:
            return {"success": False, "message": f"查询失败: {str(e)}"}
        finally:
            conn.close()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 主键值使用参数化查询，杜绝 SQL 注入
            cursor.execute(f"DELETE FROM `{table}` WHERE `{pk_field}` = %s", (pk_value,))
            affected = cursor.rowcount
        conn.commit()
        return {
            "success": True,
            "message": f"已删除表 {table} 中 {pk_field}={pk_value} 的 {affected} 行数据",
            "affected": affected,
        }
    except Exception as e:
        return {"success": False, "message": f"删除失败: {str(e)}"}
    finally:
        conn.close()


def delete_user_all_data(identifier: str) -> dict:
    """管理员：删除指定用户名或用户ID的账号及其所有 MySQL 数据。

    identifier 可以是纯数字（按 id）或用户名（按 username）。
    删除范围：users 表账号 + user_imports 导入记录 + user_llm_config LLM配置。
    返回 {"success", "message", "deleted": {...}}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 定位目标用户
            if str(identifier).isdigit():
                cursor.execute("SELECT id, username FROM users WHERE id = %s", (int(identifier),))
            else:
                cursor.execute("SELECT id, username FROM users WHERE username = %s", (identifier,))
            user = cursor.fetchone()
            if not user:
                return {"success": False, "message": f"未找到用户：{identifier}"}

            uid = user["id"]
            uname = user["username"]

            # 保护：禁止删除管理员账号自身
            if is_admin_user(uname):
                return {"success": False, "message": "不能删除管理员账号"}

            # 2. 删除该用户在各表中的数据
            counts = {}
            cursor.execute("DELETE FROM user_imports WHERE user_id = %s", (uid,))
            counts["user_imports"] = cursor.rowcount
            cursor.execute("DELETE FROM user_llm_config WHERE user_id = %s", (uid,))
            counts["user_llm_config"] = cursor.rowcount
            cursor.execute("DELETE FROM users WHERE id = %s", (uid,))
            counts["users"] = cursor.rowcount

        conn.commit()
        return {
            "success": True,
            "message": f"已删除用户「{uname}」(id={uid}) 的全部数据库数据",
            "deleted": counts,
        }
    except Exception as e:
        return {"success": False, "message": f"删除失败: {str(e)}"}
    finally:
        conn.close()
