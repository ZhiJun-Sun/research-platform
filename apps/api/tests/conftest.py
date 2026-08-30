"""测试公共夹具。"""

import os

# 测试默认使用全 Fake 后端，与外部环境完全解耦
os.environ.setdefault("HYDROLAB_ENVIRONMENT", "test")
os.environ.setdefault("HYDROLAB_OBJECT_STORAGE_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_TASK_QUEUE_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_EXPERIMENT_TRACKER_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_RUN_EXECUTOR_BACKEND", "fake")
