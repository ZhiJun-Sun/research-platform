"""领域枚举（稳定契约，前端只能依赖这些值，不依赖展示文案）。"""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Role(StrEnum):
    """资源级角色（plans/02 第 3.2 节：首版仅 OWNER / VIEWER）。"""

    OWNER = "OWNER"
    VIEWER = "VIEWER"


class SubjectType(StrEnum):
    USER = "USER"


class ResourceType(StrEnum):
    """可授权资源类型。B1 仅定义，具体资源在后续批次实现。"""

    DATASET = "DATASET"
    CODE_REPOSITORY = "CODE_REPOSITORY"
    EXPERIMENT_TEMPLATE = "EXPERIMENT_TEMPLATE"
    EXPERIMENT = "EXPERIMENT"
    RUN = "RUN"
    CHECKPOINT = "CHECKPOINT"
    RESULT = "RESULT"
    RUNTIME_ENVIRONMENT = "RUNTIME_ENVIRONMENT"


class AuditAction(StrEnum):
    ADMIN_BOOTSTRAPPED = "admin.bootstrapped"
    INVITATION_CREATED = "invitation.created"
    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_REVOKED = "invitation.revoked"
    USER_LOGIN = "user.login"
    GRANT_CREATED = "grant.created"
    GRANT_REVOKED = "grant.revoked"
    SHARE_LINK_CREATED = "share_link.created"
    SHARE_LINK_REVOKED = "share_link.revoked"
    SHARE_LINK_ACCESSED = "share_link.accessed"
