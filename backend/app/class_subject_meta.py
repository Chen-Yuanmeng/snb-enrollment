from .rules_loader import get_grade_class_subject_groups, get_grade_class_subject_options


GRADE_CLASS_SUBJECT_GROUPS: dict[str, list[list[str]]] = get_grade_class_subject_groups()

GRADE_CLASS_SUBJECT_OPTIONS: dict[str, set[str]] = get_grade_class_subject_options()
