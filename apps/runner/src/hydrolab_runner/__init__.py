"""HydroLab Runner Controller（B0 占位）。

职责（plans/02 第 9 节）：RunSpec 校验、GPU 租约、隔离容器生命周期。
安全边界：API 进程不持有 Docker Socket；镜像 digest 白名单；非 root；
只读输入挂载；默认禁网。真实 Docker 实现需先通过 Runner 安全 Spike。
"""
