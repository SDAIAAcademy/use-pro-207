# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Runs the solution of every lab and prints PASS or the first difference.

  uv run labs/solutions/check.py          # every lab
  uv run labs/solutions/check.py 1.2 2.2  # some

It reads the participants' files in labs/files/ and the reference answers in labs/solutions/,
recomputes the critical path, the finish date, the status and the scores from the files
themselves, and compares them with the reference answers and with key.json. It writes nothing
and calls no language model: every file the pack attributes to the assistant was written by a
scripted stand-in.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE.parent / "files"
KEY = json.loads((HERE / "key.json").read_text(encoding="utf-8"))
START = dt.date(2027, 4, 4)
DEADLINE = dt.date(2027, 7, 29)
STATUS_DAY = 45


def expect(name: str, got, want) -> None:
    if got != want:
        print(f"FAIL  {name}: got {got!r}, expected {want!r}")
        raise SystemExit(1)
    print(f"ok    {name}: {got}")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rows(path: Path) -> list[list[str]]:
    return list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))[1:]


def num(s: str) -> int:
    return int(s.replace(",", ""))


def lines_at(path: Path) -> dict[str, str]:
    return dict(re.findall(r"^\[(\d\d:\d\d)\] (.+)$", text(path), flags=re.M))


def holidays() -> list[dt.date]:
    return [dt.date.fromisoformat(r[0]) for r in rows(FILES / "calendar.csv")]


def workday(start: dt.date, n: int, off: list[dt.date]) -> dt.date:
    """The date n working days after start: WORKDAY.INTL(start; n; 7; off)."""
    day = start
    while n > 0:
        day += dt.timedelta(days=1)
        if day.weekday() not in (4, 5) and day not in off:
            n -= 1
    return day


def cpm(table: list[list[str]]):
    dur = {r[0]: int(r[2]) for r in table}
    pred = {r[0]: r[3].split() for r in table}
    es, ef = {}, {}
    for c in dur:
        es[c] = max((ef[p] for p in pred[c]), default=0)
        ef[c] = es[c] + dur[c]
    total = max(ef.values())
    ls, lf = {}, {}
    for c in reversed(list(dur)):
        nxt = [x for x in dur if c in pred[x]]
        lf[c] = min((ls[x] for x in nxt), default=total)
        ls[c] = lf[c] - dur[c]
    return es, ef, ls, lf, total, [c for c in dur if ls[c] == es[c]], pred


def lab_1_1() -> None:
    k = KEY["lab_1_1"]
    log = rows(HERE / "error_log.csv")
    expect("planted errors in the reference log", len(log), 10)
    kinds = [r[2] for r in log]
    expect("two errors of each kind", sorted(kinds.count(x) for x in set(kinds)), [2, 2, 2, 2, 2])
    expect("artefacts covered", sorted({r[0] for r in log}), ["A1", "A2", "A3", "A4", "A5"])
    charter = text(FILES / "charter.txt")
    m1 = lines_at(FILES / "meetings" / "m1_kickoff_ar.txt")
    # A1: the charter makes installation wait for delivery, and gives the inspection no date
    expect("charter: T07 waits for delivery", "T07 تركيب المبرّدات الجديدة: 8 أيام. لا يبدأ قبل وصول المبرّدات" in charter, True)
    expect("charter names 20 July", "20 يوليو" in charter, False)
    # A2: nobody took the access schedule, and the bidders list has no date
    expect("M1 at 16:15 assigns nobody", "لا نسنده الآن" in m1["16:15"], True)
    expect("M1 at 18:00 gives a date", bool(re.search(r"\d", m1["18:00"])), False)
    # A3: T06 is not accepted
    st = {r[0]: r for r in rows(FILES / "plan" / "tasks_status.csv")}
    expect("T06 acceptance signed", st["T06"][8], "لا")
    # A4: recompute the three quotations from the quotation files
    totals = []
    for i in (1, 2, 3):
        q = text(FILES / "quotes" / f"quote_{i}.txt")
        pairs = re.findall(r": ([\d,]+) [^×\n]+ × ([\d,]+) ريال", q)
        expect(f"lines read from quotation {i}", len(pairs), 3)
        expect(f"quotation {i} excludes VAT", "لا تشمل ضريبة القيمة المضافة" in q, True)
        totals.append(round(sum(num(a) * num(b) for a, b in pairs) * 1.15))
    expect("quotation totals with VAT", totals, k["quotes_total"])
    table = rows(FILES / "review" / "A4_price_comparison.csv")
    shown = [int(x) for x in table[4][3:6]]
    expect("the assistant's totals", shown, k["assistant_quotes_total"])
    expect("lowest quotation after recomputing", totals.index(min(totals)) + 1, 1)
    expect("lowest quotation in the assistant's table", shown.index(min(shown)) + 1, 3)
    # A5: scores multiply correctly, one owner is not in the team, one impact contradicts the approved log
    team = re.findall(r"^- ([^:\n]+):", charter.split("3. الفريق")[1].split("4. تقويم")[0], flags=re.M)
    expect("people in the team", len(team), 6)
    risk = rows(FILES / "review" / "A5_risk_log.csv")
    expect("risk scores are products", all(int(r[2]) * int(r[3]) == int(r[4]) for r in risk), True)
    expect("risk owners outside the team", [r[0] for r in risk if r[5] not in team], ["R4"])
    official = {r[0]: r for r in rows(FILES / "meetings" / "risk_log.csv")}
    expect("risks whose impact differs from the approved log", [r[0] for r in risk if r[3] != official[r[0]][3]], ["R2"])


def lab_1_2() -> None:
    k = KEY["lab_1_2"]
    table = rows(FILES / "start" / "plan_predecessors.csv")
    es, ef, ls, lf, total, critical, pred = cpm(table)
    expect("total working days", total, k["total"])
    expect("critical path", critical, k["critical"])
    crit = set(critical)
    expect("the critical path is unique", all(sum(1 for x in crit if c in pred[x]) <= 1 for c in crit), True)
    ref = rows(HERE / "plan_sheet.csv")
    expect("reference sheet agrees with the recomputation",
           all([int(x) for x in r[4:9]] == [es[r[0]], ef[r[0]], ls[r[0]], lf[r[0]], ls[r[0]] - es[r[0]]] for r in ref), True)
    blank = {r[0]: pred[r[0]] for r in rows(FILES / "plan" / "plan_sheet.csv") if not r[3] and r[0] != "T01"}
    expect("predecessors left blank", blank, k["blank_predecessors"])
    charter = text(FILES / "charter.txt")
    expect("start is the Sunday the charter names", (START.weekday(), "الأحد 4 أبريل 2027" in charter), (6, True))
    off = holidays()
    expect("non-working days in the calendar", len(off), 8)
    finish = workday(START, total - 1, off)
    expect("finish date", finish.isoformat(), k["finish"])
    expect("finish is after the deadline", finish > DEADLINE, True)
    ai = rows(FILES / "start" / "plan_ai_draft.csv")
    _, _, _, _, a_total, a_crit, _ = cpm(ai)
    expect("assistant's total", a_total, k["assistant_total"])
    expect("assistant's finish (no holidays)", workday(START, a_total - 1, []).isoformat(), k["assistant_finish"])
    expect("tasks the assistant changed", [r[0] for r, t in zip(ai, table) if r[2] != t[2] or r[3] != t[3]], ["T07", "T11"])
    expect("assistant's summary names its own path", " ← ".join(a_crit) in text(FILES / "start" / "plan_ai_summary.txt"), True)
    # status under the written rules
    st = rows(FILES / "plan" / "tasks_status.csv")
    planned = sum(int(r[2]) for r in st if int(r[4]) <= STATUS_DAY)
    earned = sum(int(r[2]) for r in st if r[8] == "نعم")
    weight = sum(int(r[2]) for r in st)
    index = round(earned / planned, 3)
    colour = "أخضر" if index >= 0.95 else "أصفر" if index >= 0.85 else "أحمر"
    s = k["status"]
    expect("planned, earned, weight", [planned, earned, weight], [s["planned"], s["earned"], s["total_weight"]])
    expect("schedule index and colour", [index, colour], [s["index"], s["colour"]])
    expect("percent complete", round(100 * earned / weight, 1), s["percent_complete"])
    started = [int(r[7]) for r in st if r[5] != ""]
    expect("the assistant's percent is the mean of the reported percents", round(sum(started) / len(started)), s["assistant_percent"])
    expect("status date", workday(START, STATUS_DAY - 1, off).isoformat(), "2027-06-10")


def lab_2_1() -> None:
    k = KEY["lab_2_1"]
    tr = {"M1": lines_at(FILES / "meetings" / "m1_kickoff_ar.txt"), "M2": lines_at(FILES / "meetings" / "m2_prebid_en.txt"),
          "M3": lines_at(FILES / "meetings" / "m3_progress_ar.txt")}
    reg = rows(HERE / "action_register.csv")
    expect("entries in the reference register", len(reg), k["entries"])
    expect("entries whose time is not in their transcript", [r[0] for r in reg if r[6] not in tr[r[1]]], [])
    en = {"جليلة الخثعمي": "Jalila", "فاضل الرومي": "Fadel", "حاتم الدوسري": "Hatim"}
    missing = []
    for r in reg:
        if r[4] == "لم يُسند":
            continue
        who = en[r[4]] if r[1] == "M2" else r[4].split()[0]
        if who not in tr[r[1]][r[6]]:
            missing.append(r[0])
    expect("owners not named in the cited line", missing, [])
    off = holidays()
    bad = [r[0] for r in reg if re.fullmatch(r"\d{4}-\d\d-\d\d", r[5])
           and (dt.date.fromisoformat(r[5]).weekday() in (4, 5) or dt.date.fromisoformat(r[5]) in off)]
    expect("due dates that are not working days", bad, [])
    draft = rows(FILES / "start" / "actions_ai_draft.csv")
    expect("rows in the assistant's draft", len(draft), k["draft_rows"])
    good = {tuple(r[1:6]) for r in reg}
    wrong = [r for r in draft if tuple(r[:5]) not in good]
    expect("wrong rows, missing rows", [len(wrong), len(reg) - len(draft)], [6, 2])
    expect("faults in the key", len(k["faults"]), 8)
    late = {m: t for m, t in (("M2", "05:50"), ("M3", "17:00")) if re.search(r"joins|انضمت", tr[m][t])}
    expect("people who joined after the recording notice", late, k["late_joiners"])
    expect("each transcript opens with the recording notice", [bool(re.search(r"recorded|مسجَّل", t["00:00"])) for t in tr.values()], [True, True, True])
    risk = {r[0]: r for r in rows(FILES / "meetings" / "risk_log.csv")}
    expect("R2 before the meetings", [int(x) for x in risk["R2"][2:5]], [3, 5, 15])
    expect("R2 after the meetings", [5, int(risk["R2"][3]), 5 * int(risk["R2"][3])], k["risk_R2"])


def score(values: dict[str, list[float]], weights: list[int]) -> dict[str, float]:
    """The rules of files/proposals/scoring_rules.txt."""
    low, fast = min(v[0] for v in values.values()), min(v[2] for v in values.values())
    out = {}
    for b, (price, met, days, years, judge) in values.items():
        parts = [100 * low / price, 100 * met / 8, 100 * fast / days, min(100, 100 * years / 5), 100 * judge / 5]
        out[b] = round(sum(w * p for w, p in zip(weights, parts)) / 100, 2)
    return out


def lab_2_2() -> None:
    k = KEY["lab_2_2"]
    weights = [int(r[2]) for r in rows(FILES / "proposals" / "criteria.csv")]
    expect("weights add up to 100", sum(weights), 100)
    files = {"A": "proposal_A_naseem.txt", "B": "proposal_B_zamhareer.txt", "C": "proposal_C_polarline.txt"}
    pages = {b: re.split(r"=====[^=]+=====\n", text(FILES / "proposals" / f))[1:] for b, f in files.items()}
    expect("pages per proposal", [len(p) for p in pages.values()], [6, 6, 6])
    # prices read from page 5, VAT added where the page says it is excluded
    price = {}
    for b, p in pages.items():
        raw = num(re.search(r"(\d,\d{3},\d{3})", p[4]).group(1))
        price[b] = round(raw * 1.15) if "لا تشمل" in p[4] else raw
    # requirements not met, read from the compliance table on page 4
    unmet = {"A": len(re.findall(r"غير مستوفى", pages["A"][3])), "B": len(re.findall(r"غير مستوفى", pages["B"][3])),
             "C": len(re.findall(r"Q\d: ", pages["C"][3]))}
    matrix = rows(HERE / "matrix.csv")
    values = {b: [float(r[3]) for r in matrix if r[2] == b and r[0].startswith("C")] for b in files}
    expect("prices in the matrix come from page 5", {b: int(v[0]) for b, v in values.items()}, price)
    expect("requirements met come from page 4", {b: int(v[1]) for b, v in values.items()}, {b: 8 - n for b, n in unmet.items()})
    expect("matrix values equal the key", {b: [int(x) for x in v] for b, v in values.items()}, k["true"])
    got = score(values, weights)
    expect("weighted totals", got, k["scores"])
    expect("totals written in the matrix", {r[2]: float(r[6]) for r in matrix if r[0] == "المجموع"}, got)
    rank = sorted(got, key=lambda b: -got[b])
    expect("ranking", rank, k["rank"])
    ex = rows(FILES / "start" / "extracted_values.csv")
    ai = {b: [float(r[2]) for r in ex if r[1] == b] for b in files}
    ai_got = score(ai, weights)
    expect("totals from the assistant's values", ai_got, k["assistant_scores"])
    ai_rank = sorted(ai_got, key=lambda b: -ai_got[b])
    expect("the assistant's ranking", ai_rank, k["assistant_rank"])
    expect("the winner changes after verification", ai_rank[0] != rank[0], True)
    note = text(FILES / "start" / "evaluation_ai_note.txt")
    expect("the assistant's written totals can be recomputed", any(f"{v:.1f}" in note for v in ai_got.values()), False)
    for b in files:  # the winner holds when one judgement moves by one point
        for d in (-1, 1):
            v = {x: list(y) for x, y in values.items()}
            v[b][4] = min(5, max(0, v[b][4] + d))
            s = score(v, weights)
            if max(s, key=lambda x: s[x]) != rank[0]:
                expect(f"winner when the judgement of {b} moves by {d}", max(s, key=lambda x: s[x]), rank[0])
    print("ok    the winner holds when any one judgement moves by one point")
    decl = text(FILES / "proposals" / "declarations.txt")
    expect("a stood-down evaluator is named in the assistant's note", "يتنحى فاضل الرومي" in decl and "فاضل الرومي" in note, True)
    expect("the estimate appears in the assistant's note", "التكلفة التقديرية البالغة" in note, True)


LABS = {"1.1": lab_1_1, "1.2": lab_1_2, "2.1": lab_2_1, "2.2": lab_2_2}

if __name__ == "__main__":
    for lab in sys.argv[1:] or list(LABS):
        print(f"--- lab {lab}")
        LABS[lab]()
        print(f"PASS  lab {lab}")
