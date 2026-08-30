"""不透明令牌生成与哈希。

- 原始 token 使用 secrets.token_urlsafe，仅在创建响应中返回一次；
- 存储与查询一律使用 HMAC-SHA256(secret, token)，数据库/内存中不出现明文；
- 日志中禁止记录原始 token。
"""

import hashlib
import hmac
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
