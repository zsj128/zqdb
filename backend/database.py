"""
用户数据库操作模块
基于 pymysql 连接 MySQL (zqdb_db)
"""
import pymysql


# ============================================================
# 数据库配置
# ============================================================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Aa@1233211234567",
    "db": "zqdb_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def get_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def init_user_table():
    """初始化用户表（如果不存在）"""
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
        conn.commit()
        print("✅ 用户表初始化完成")
    finally:
        conn.close()


def register_user(username: str, password: str, email: str = "", phone: str = "") -> dict:
    """
    用户注册
    返回: {"success": bool, "message": str}
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查用户名是否已存在
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
                return {"success": False, "message": "用户名或密码错误", "user_id": None, "username": None}

            if user["password"] != password:
                return {"success": False, "message": "用户名或密码错误", "user_id": None, "username": None}

            return {
                "success": True,
                "message": "登录成功",
                "user_id": user["id"],
                "username": user["username"]
            }
    except Exception as e:
        return {"success": False, "message": f"登录失败: {str(e)}", "user_id": None, "username": None}
    finally:
        conn.close()


# if __name__ == "__main__":
#     # 测试：初始化数据库
#     init_user_table()
