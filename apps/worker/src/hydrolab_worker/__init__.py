"""HydroLab Worker（B0 占位）。

职责（plans/02 第 1 节）：导入、解析、绘图、导出、MLflow 同步等异步任务。
QUEUE-01 Spike 通过前，仅消费 FakeTaskQueue 的内存消息；
消费端按 job_id + attempt 幂等，Celery task ID 仅作关联。
"""
