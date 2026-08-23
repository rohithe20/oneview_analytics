import enum


class ExamSession(enum.Enum):
    MARCH = "March"
    MAY_JUNE = "May/June"
    OCT_NOV = "Oct/Nov"


class AttemptStatus(enum.Enum):
    DRAFT = "Draft"
    COMPLETED = "Completed"