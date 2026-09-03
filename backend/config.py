# -*- coding: utf-8 -*-
"""
全局配置模块：路径常量、文本处理常量、容错设置。

从 main.py 拆出，集中管理魔法数字与路径，便于统一调整。
"""
import os
import sys

# backend 目录（本文件所在目录）
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

# ============================================================
# 路径
# ============================================================

def _user_data_dir():
    """用户数据根目录（像系统软件一样存到当前用户目录下的 .law_ai）。

    查找顺序：
      1. 环境变量 LAW_AI_HOME 指定的路径（Docker 部署时便于挂载）
      2. 当前用户主目录下的 .law_ai（如 C:\\Users\\Administrator\\.law_ai）
    """
    env = os.environ.get("LAW_AI_HOME", "")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.expanduser("~"), ".law_ai")


# 知识库向量数据目录（ChromaDB），默认存到 ~/.law_ai/chroma_kb
CHROMA_PATH = os.path.join(_user_data_dir(), 'chroma_kb')
# 上传落盘目录（data/upload），默认存到 ~/.law_ai/data
_DATA_HOME = os.path.join(_user_data_dir(), 'data')
DATA_DIR = os.environ.get("DATA_DIR", _DATA_HOME)
LAW_DIR = os.path.join(DATA_DIR, 'law')
SAMPLE_DIR = os.path.join(DATA_DIR, 'sample')

# ============================================================
# LLM 默认配置
# ============================================================
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ============================================================
# 文本检索常量
# ============================================================
STOP_WORDS = {'怎么', '什么', '如何', '哪些', '哪个', '多少', '是否',
              '的', '了', '在', '是', '有', '和', '与', '或',
              '。', '：', '；', '、', '，', '？', '！', '“', '”', '（', '）', '《', '》', '【', '】', '（', '）'}

# 每个用户目录内的固定集合名（ChromaDB 要求 3-512 个字符，且仅含字母数字._-）
KB_COLLECTION_NAME = "legal_kb"


# ============================================================
# 容错设置（超时 / 重试 / 熔断，参考 day63）
# ============================================================
class ResilienceSettings:
    request_timeout: float = 30.0        # 单次 LLM 调用超时（秒）
    max_retries: int = 2                 # 重试次数上限
    retry_base_delay: float = 0.5        # 指数退避起始延迟（秒）
    circuit_threshold: int = 3           # 连续失败几次后熔断
    circuit_cooldown: float = 15.0       # 熔断后冷却时间（秒）
