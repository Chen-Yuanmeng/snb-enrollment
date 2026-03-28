def archive_student_grade(enrollment_grade: str) -> str:
    if enrollment_grade in {"道法押题", "五一中考", "新高一暑"}:
        return "2029届"
    if enrollment_grade == "新高二暑":
        return "2028届"
    if enrollment_grade == "新高三暑":
        return "2027届"
    if enrollment_grade == "初中/小学暑期":
        return "初中/小学"
    return enrollment_grade


def history_grade_candidates(input_grade: str) -> set[str]:
    trimmed = (input_grade or "").strip()
    if not trimmed:
        return set()

    canonical = archive_student_grade(trimmed)
    aliases: dict[str, set[str]] = {
        "2029届": {"2029届", "道法押题", "五一中考", "新高一暑"},
        "2028届": {"2028届", "新高二暑"},
        "2027届": {"2027届", "新高三暑"},
        "初中/小学": {"初中/小学", "初中/小学暑期"},
    }
    return aliases.get(canonical, {trimmed})
