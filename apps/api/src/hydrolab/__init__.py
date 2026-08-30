"""HydroLab 平台后端 API 包。

业务语义（Run 状态机、权限、不可变版本、GPU 租约）由本包自有；
基础设施能力仅通过 `hydrolab.ports` 定义的端口访问，
具体实现位于 `hydrolab.adapters`（fake / local / 真实服务）。
"""

__version__ = "0.1.0"
