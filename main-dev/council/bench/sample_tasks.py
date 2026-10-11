"""Sample benchmark generator (spec 18.1). Writes bench/tasks/sample.jsonl.

48 hand-checked tasks: 8 categories x 6 tasks, 2 easy, 2 medium, 2 hard per category.
Answer types are mcq, numeric and exact only. Split is stratified by category:
50% calibration (24 tasks, enough for Tier B), the rest test.

Run from the repo root:  python -m council.bench.sample_tasks
"""

from __future__ import annotations

import json
from pathlib import Path

from council.core.schemas import BenchTask

SOURCE = "council-sample-v1"
CATEGORIES = ["math", "logic", "code", "science", "knowledge", "reading", "writing", "planning"]
NUMERIC_TOL = 1e-6

# Each category lists its 6 tasks in this order: easy, medium, hard, easy, medium, hard.
# Tuple: (difficulty, answer_type, prompt, choices, answer)
_RAW: dict[str, list[tuple]] = {
    "math": [
        ("easy", "numeric", "What is 17 * 23?", None, "391"),
        ("medium", "numeric", "What is the sum of all integers from 1 to 100 inclusive?", None, "5050"),
        ("hard", "numeric", "How many positive divisors does 360 have?", None, "24"),
        ("easy", "mcq",
         "Which of these is prime?\nA) 51\nB) 57\nC) 61\nD) 63",
         ["A 51", "B 57", "C 61", "D 63"], "C"),
        ("medium", "mcq",
         "What is the derivative of x^3 + 2x, evaluated at x = 2?\nA) 10\nB) 12\nC) 14\nD) 8",
         ["A 10", "B 12", "C 14", "D 8"], "C"),
        ("hard", "numeric", "What is the remainder when 2^100 is divided by 7?", None, "2"),
    ],
    "logic": [
        ("easy", "mcq",
         "All bloops are razzies. All razzies are lazzies. Are all bloops lazzies?\n"
         "A) yes\nB) no\nC) cannot tell",
         ["A yes", "B no", "C cannot tell"], "A"),
        ("medium", "numeric",
         "How many of the 8 possible truth assignments to three statements p, q, r make both "
         "'p implies q' and 'q implies r' true? Answer with a number.",
         None, "4"),
        ("hard", "mcq",
         "Which statement is the negation of 'For every x there exists y such that x < y'?\n"
         "A) There exists x such that for every y, x < y.\n"
         "B) There exists x such that for every y, x >= y.\n"
         "C) For every x and every y, x >= y.\n"
         "D) There exists x and y such that x >= y.",
         ["A There exists x such that for every y, x < y.",
          "B There exists x such that for every y, x >= y.",
          "C For every x and every y, x >= y.",
          "D There exists x and y such that x >= y."], "B"),
        ("easy", "numeric", "Continue the sequence 2, 4, 8, 16, ___. What is the next number?", None, "32"),
        ("medium", "exact",
         "A man looks at a portrait and says: 'Brothers and sisters I have none, but that man's "
         "father is my father's son.' Whose portrait is it? Answer with one word.",
         None, "son"),
        ("hard", "mcq",
         "Which statement is the contrapositive of 'If it snows, school is closed'?\n"
         "A) If school is closed, it snows.\n"
         "B) If school is open, it does not snow.\n"
         "C) If it does not snow, school is open.\n"
         "D) If school is closed, it does not snow.",
         ["A If school is closed, it snows.",
          "B If school is open, it does not snow.",
          "C If it does not snow, school is open.",
          "D If school is closed, it does not snow."], "B"),
    ],
    "code": [
        ("easy", "numeric", "In Python, what does len([1, 2, [3, 4], 5]) return?", None, "4"),
        ("medium", "numeric",
         "What does this Python program print?\nx = [i * i for i in range(5)]\nprint(sum(x))",
         None, "30"),
        ("hard", "numeric",
         "The naive recursive function fib(n) returns 0 for n = 0, 1 for n = 1, and "
         "fib(n-1) + fib(n-2) otherwise. Count every call to fib, including the first call fib(5). "
         "How many calls are made in total?",
         None, "15"),
        ("easy", "mcq",
         "Which data structure gives first-in, first-out order?\nA) stack\nB) queue\nC) heap\nD) tree",
         ["A stack", "B queue", "C heap", "D tree"], "B"),
        ("medium", "mcq",
         "What is the worst-case time complexity of binary search on a sorted array of n items?\n"
         "A) O(1)\nB) O(n)\nC) O(log n)\nD) O(n log n)",
         ["A O(1)", "B O(n)", "C O(log n)", "D O(n log n)"], "C"),
        ("hard", "exact",
         "A binary search tree is a single path of n nodes, with every insertion going to the "
         "deepest leaf. In big-O terms, what is the worst-case time to insert one key? "
         "Answer with one word.",
         None, "linear"),
    ],
    "science": [
        ("easy", "exact", "What gas do plants take in for photosynthesis? Answer in two words.",
         None, "carbon dioxide"),
        ("medium", "numeric",
         "What is the boiling point of water in degrees Celsius at standard sea-level pressure?",
         None, "100"),
        ("hard", "numeric",
         "What is the speed of light in vacuum in km/s, rounded to the nearest integer, "
         "using c = 299792.458 km/s?",
         None, "299792"),
        ("easy", "mcq", "What is the chemical symbol for sodium?\nA) So\nB) Na\nC) Sd\nD) S",
         ["A So", "B Na", "C Sd", "D S"], "B"),
        ("medium", "mcq", "Which particle has no electric charge?\nA) proton\nB) electron\n"
         "C) neutron\nD) positron",
         ["A proton", "B electron", "C neutron", "D positron"], "C"),
        ("hard", "numeric", "A 2 kg object moves at 3 m/s. What is its kinetic energy in joules?",
         None, "9"),
    ],
    "knowledge": [
        ("easy", "exact", "What is the capital of Australia? Answer with one word.", None, "canberra"),
        ("medium", "mcq", "Who wrote the novel 'Pride and Prejudice'?\nA) Charlotte Bronte\n"
         "B) Jane Austen\nC) Mary Shelley\nD) George Eliot",
         ["A Charlotte Bronte", "B Jane Austen", "C Mary Shelley", "D George Eliot"], "B"),
        ("hard", "exact", "Which chemical element has atomic number 79? Answer with one word.",
         None, "gold"),
        ("easy", "numeric", "How many continents are there in the usual seven-continent model?",
         None, "7"),
        ("medium", "exact", "What is the largest planet in the Solar System? Answer with one word.",
         None, "jupiter"),
        ("hard", "mcq", "In what year did the Peace of Westphalia end the Thirty Years' War?\n"
         "A) 1618\nB) 1648\nC) 1715\nD) 1815",
         ["A 1618", "B 1648", "C 1715", "D 1815"], "B"),
    ],
    "reading": [
        ("easy", "mcq",
         "Passage: 'Mia bought three apples and two pears. She gave one apple away.' "
         "How many pieces of fruit does Mia have now?\nA) 3\nB) 4\nC) 5\nD) 6",
         ["A 3", "B 4", "C 5", "D 6"], "B"),
        ("medium", "numeric",
         "Passage: 'The train left at 9:15 and arrived at 11:45 the same day.' "
         "How many minutes did the trip take?",
         None, "150"),
        ("hard", "exact",
         "Passage: 'Everyone in the club who plays chess also plays go. Nobody who plays go is "
         "afraid of losses. Dana plays chess.' Does Dana play go? Answer yes, no, or cannot say.",
         None, "yes"),
        ("easy", "exact",
         "Passage: 'The dog barked all night. The neighbors complained.' Who complained? "
         "Answer with one word.",
         None, "neighbors"),
        ("medium", "mcq",
         "Passage: 'Sales rose 10% in March, then fell 10% in April.' Compared with the start of "
         "March, sales in late April are:\nA) higher\nB) the same\nC) lower\nD) cannot tell",
         ["A higher", "B the same", "C lower", "D cannot tell"], "C"),
        ("hard", "numeric",
         "Passage: 'A recipe needs 3 cups of flour for 12 cookies. Ella wants 30 cookies.' "
         "How many cups of flour does she need?",
         None, "7.5"),
    ],
    "writing": [
        ("easy", "exact", "What is the plural of 'mouse'? Answer with one word.", None, "mice"),
        ("medium", "mcq",
         "Which sentence is grammatically correct?\n"
         "A) Neither the boys nor the girl were ready.\n"
         "B) Neither the boys nor the girl was ready.\n"
         "C) Neither the boys nor the girl are ready.\n"
         "D) Neither the boys nor the girls is ready.",
         ["A Neither the boys nor the girl were ready.",
          "B Neither the boys nor the girl was ready.",
          "C Neither the boys nor the girl are ready.",
          "D Neither the boys nor the girls is ready."], "B"),
        ("hard", "exact",
         "Which literary device is shown in 'the wind whispered through the trees'? "
         "Answer with one word.",
         None, "personification"),
        ("easy", "mcq", "Which word is a synonym of 'happy'?\nA) sad\nB) joyful\nC) angry\nD) tired",
         ["A sad", "B joyful", "C angry", "D tired"], "B"),
        ("medium", "numeric", "How many letters are in the word 'rhythm'?", None, "6"),
        ("hard", "mcq", "Which is spelled correctly?\nA) accomodate\nB) accommodate\n"
         "C) acommodate\nD) accomodeate",
         ["A accomodate", "B accommodate", "C acommodate", "D accomodeate"], "B"),
    ],
    "planning": [
        ("easy", "numeric",
         "A meeting starts at 2:00 pm and lasts 75 minutes. How many minutes past 3:00 pm does it end?",
         None, "15"),
        ("medium", "mcq",
         "A bus leaves every 20 minutes, starting at 8:00. Which of these is a departure time?\n"
         "A) 8:50\nB) 8:45\nC) 8:40\nD) 8:55",
         ["A 8:50", "B 8:45", "C 8:40", "D 8:55"], "C"),
        ("hard", "numeric",
         "Task A takes 4 hours. Task B takes 3 hours and can only start after A finishes. Task C "
         "takes 2 hours and is independent. Two workers each do one task at a time. What is the "
         "minimum number of hours to finish all three?",
         None, "7"),
        ("easy", "exact", "Which day of the week comes after Friday? Answer with one word.",
         None, "saturday"),
        ("medium", "mcq",
         "Roads: A-B has length 1, B-C has length 2, A-C has length 4. What is the shortest "
         "distance from A to C?\nA) 4\nB) 3\nC) 2\nD) 1",
         ["A 4", "B 3", "C 2", "D 1"], "B"),
        ("hard", "numeric",
         "A job needs 240 units of work at 12 units per hour. After every full 4 hours of work "
         "there is a 1-hour break, except that no break follows the final hour of work. "
         "How many hours in total, counting work and breaks?",
         None, "24"),
    ],
}

_GRADER = {
    "mcq": {"type": "mcq"},
    "exact": {"type": "exact"},
    "numeric": {"type": "numeric_tolerance", "tolerance": NUMERIC_TOL},
}


def _split_for(category_index: int, position: int) -> str:
    """Calibration: positions 0, 2 and 4 (easy, hard, medium) in every category, so each
    category has 3 calibration and 3 test tasks, one of each difficulty in both. 24 of 48."""
    return "calibration" if position in (0, 2, 4) else "test"


def generate() -> list[dict]:
    rows: list[dict] = []
    for ci, category in enumerate(CATEGORIES):
        for pos, (difficulty, answer_type, prompt, choices, answer) in enumerate(_RAW[category]):
            task = {
                "id": f"sample-{category}-{pos + 1:02d}",
                "source": SOURCE,
                "category": category,
                "difficulty": difficulty,
                "split": _split_for(ci, pos),
                "prompt": prompt,
                "choices": choices,
                "answer_type": answer_type,
                "answer": answer,
                "grader": dict(_GRADER[answer_type]),
            }
            rows.append(task)
    return rows


def default_path() -> Path:
    return Path(__file__).resolve().parents[2] / "bench" / "tasks" / "sample.jsonl"


def main(path: Path | None = None) -> Path:
    out = Path(path) if path is not None else default_path()
    rows = generate()
    for row in rows:  # validate against the contract before writing
        BenchTask.model_validate(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    print(main())
