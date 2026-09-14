"""实验/Run 领域错误。"""


class StaleStateError(Exception):
    """Run 状态 CAS 失败：期望的前置状态与实际不一致，或试图覆盖终态。

    由 RunStore.save(expected_status=...) 在原子 UPDATE 未命中任何行时抛出，
    调用方据此判定「状态已被并发方推进 / 已收敛到终态」，可安全重试或直接返回。
    """

    def __init__(self, message: str = "Run 状态已被并发变更或已进入终态") -> None:
        super().__init__(message)