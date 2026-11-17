# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Writes the synthetic file pack of USE-PRO-207 into labs/files/ and the trainer's key and
reference answers into labs/solutions/. Standard library only, fixed seed, the same bytes on
every run.

  uv run labs/_tools/prepare_files.py

Everything here is invented: the centre, the project, the suppliers, the people, the meetings
and every figure. No language model is called: each file the pack attributes to the assistant
was written by hand as a scripted stand-in, with its faults planted on purpose.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pack_day1 as d1  # noqa: E402
import pack_day2 as d2  # noqa: E402

SEED = 207
LABS = Path(__file__).resolve().parent.parent
FILES = LABS / "files"
SOL = LABS / "solutions"

START = dt.date(2027, 4, 4)
HOLIDAYS = [dt.date(2027, 5, d) for d in range(16, 21)] + [dt.date(2027, 6, d) for d in range(13, 16)]
DEADLINE = dt.date(2027, 7, 29)
STATUS_DAY = 45
WEEKEND = {4, 5}  # Friday and Saturday (Monday is 0)
DAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# code, name, duration in working days, predecessors
TASKS = [
    ("T01", "اعتماد التصميم والمواصفات", 5, []),
    ("T02", "طرح المنافسة واستلام العروض", 15, ["T01"]),
    ("T03", "تقييم العروض والترسية", 8, ["T02"]),
    ("T04", "توقيع العقد وتجهيز المقاول", 5, ["T03"]),
    ("T05", "توريد المبرّدات: التصنيع والشحن إلى الموقع", 30, ["T04"]),
    ("T06", "إزالة المبرّدات القديمة وتجهيز القواعد", 10, ["T04"]),
    ("T07", "تركيب المبرّدات الجديدة", 8, ["T05", "T06"]),
    ("T08", "تمديدات المياه المبرَّدة ووحدات مناولة الهواء", 12, ["T06"]),
    ("T09", "لوحة إنذار الحريق والكواشف", 15, ["T04"]),
    ("T10", "الربط بنظام إدارة المبنى", 6, ["T07", "T08", "T09"]),
    ("T11", "الاختبار والتشغيل التجريبي", 7, ["T10"]),
    ("T12", "فحص السلامة من الجهة المختصة", 3, ["T11"]),
    ("T13", "تدريب فريق التشغيل ووثائق التسليم", 4, ["T11"]),
    ("T14", "التسليم النهائي", 1, ["T12", "T13"]),
]
# The predecessors the participants' sheet leaves blank (lab 1.2, step 1)
BLANK_PREDS = ["T07", "T08", "T10", "T14"]
# The assistant's plan: one predecessor dropped, one duration changed, non-working days ignored
AI_TASKS = [(c, n, (5 if c == "T11" else d), (["T06"] if c == "T07" else p)) for c, n, d, p in TASKS]

# code: actual start day, actual finish day, percent the owner reported, acceptance signed
STATUS = {
    "T01": (0, 5, 100, True), "T02": (5, 20, 100, True), "T03": (20, 30, 100, True),
    "T04": (30, 38, 100, True), "T05": (38, None, 20, False), "T06": (38, None, 90, False),
    "T09": (40, None, 50, False),
}


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip("\n") + "\n", encoding="utf-8", newline="\n")


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8-sig", newline="\n")


def is_working(day: dt.date, holidays=HOLIDAYS) -> bool:
    return day.weekday() not in WEEKEND and day not in holidays


def workday(start: dt.date, n: int, holidays=HOLIDAYS) -> dt.date:
    """The date n working days after start, as WORKDAY.INTL(start; n; 7; holidays) gives it."""
    day = start
    while n > 0:
        day += dt.timedelta(days=1)
        if is_working(day, holidays):
            n -= 1
    return day


def ar_date(day: dt.date) -> str:
    months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    return f"{DAY_NAMES[day.weekday()]} {day.day} {months[day.month - 1]} {day.year}"


def cpm(tasks):
    """Forward and backward pass. Days are counted from 0: a task runs from ES to EF = ES + duration."""
    dur = {c: d for c, _, d, _ in tasks}
    pred = {c: p for c, _, _, p in tasks}
    es, ef = {}, {}
    for c, _, d, p in tasks:  # the list is in a valid order
        es[c] = max((ef[x] for x in p), default=0)
        ef[c] = es[c] + d
    total = max(ef.values())
    succ = {c: [x for x in pred if c in pred[x]] for c in dur}
    ls, lf = {}, {}
    for c, _, d, _ in reversed(tasks):
        lf[c] = min((ls[x] for x in succ[c]), default=total)
        ls[c] = lf[c] - d
    slack = {c: ls[c] - es[c] for c in dur}
    critical = [c for c, _, _, _ in tasks if slack[c] == 0]
    return {"es": es, "ef": ef, "ls": ls, "lf": lf, "float": slack, "total": total, "critical": critical}


def status(tasks, plan):
    planned = sum(d for c, _, d, _ in tasks if plan["ef"][c] <= STATUS_DAY)
    earned = sum(d for c, _, d, _ in tasks if STATUS.get(c, (0, 0, 0, False))[3])
    total = sum(d for _, _, d, _ in tasks)
    index = earned / planned
    colour = "أخضر" if index >= 0.95 else "أصفر" if index >= 0.85 else "أحمر"
    started = [STATUS[c][2] for c in STATUS]
    return {"planned": planned, "earned": earned, "total_weight": total, "index": round(index, 3),
            "colour": colour, "percent_complete": round(100 * earned / total, 1),
            "assistant_percent": round(sum(started) / len(started))}


def main() -> None:
    random.seed(SEED)
    for folder in (FILES,):
        if folder.exists():
            shutil.rmtree(folder)
    SOL.mkdir(parents=True, exist_ok=True)

    plan = cpm(TASKS)
    ai = cpm(AI_TASKS)
    assert plan["total"] == 89 and ai["total"] == 71, (plan["total"], ai["total"])
    # one critical path only: every critical task has at most one critical successor
    crit = set(plan["critical"])
    for c in crit:
        assert sum(1 for x, _, _, p in TASKS if c in p and x in crit) <= 1, c
    finish = workday(START, plan["total"] - 1)
    ai_finish = workday(START, ai["total"] - 1, holidays=[])
    assert ai_finish < DEADLINE < finish
    status_date = workday(START, STATUS_DAY - 1)
    st = status(TASKS, plan)
    assert st["colour"] == "أحمر"

    ctx = {
        "START": START, "HOLIDAYS": HOLIDAYS, "DEADLINE": DEADLINE, "TASKS": TASKS, "AI_TASKS": AI_TASKS,
        "BLANK_PREDS": BLANK_PREDS, "STATUS": STATUS, "STATUS_DAY": STATUS_DAY, "plan": plan, "ai": ai,
        "finish": finish, "ai_finish": ai_finish, "status_date": status_date, "st": st,
        "ar_date": ar_date, "workday": workday, "write": write, "write_csv": write_csv,
        "FILES": FILES, "SOL": SOL,
    }
    key = {"seed": SEED}
    key.update(d1.build(ctx))
    key.update(d2.build(ctx))
    write(SOL / "key.json", json.dumps(key, ensure_ascii=False, indent=2))
    n = sum(1 for p in FILES.rglob("*") if p.is_file())
    print(f"wrote {n} files into labs/files and the key into labs/solutions")
    print(f"plan: {plan['total']} working days, finish {finish}, critical {'-'.join(plan['critical'])}")
    print(f"assistant's plan: {ai['total']} working days, finish {ai_finish}")
    print(f"status on day {STATUS_DAY} ({status_date}): planned {st['planned']}, earned {st['earned']}, index {st['index']}, {st['percent_complete']}%")


if __name__ == "__main__":
    main()
