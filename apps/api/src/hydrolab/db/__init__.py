"""数据库接入层。

- Base：SQLAlchemy 声明式基类，所有 ORM 模型继承它；
- engine/session：MySQL(asyncmy) 异步引擎与会话工厂，由 Settings.database_backend 控制；
- models：与 hydrolab 领域实体一一对应的 ORM 表模型；
- repositories：实现各领域 Repository Protocol 的 SQL 仓储。
"""

from hydrolab.db.base import Base

__all__ = ["Base"]
