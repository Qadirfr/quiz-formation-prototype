from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.db_runtime import get_database_mode  # noqa: E402
from utils.question_bank import get_question_bank_stats, list_bank_domains  # noqa: E402
from utils.database import list_saved_quizzes  # noqa: E402


def main() -> None:
    print("Mode base :", get_database_mode())
    print("Quiz sauvegardés :", len(list_saved_quizzes(limit=1000)))

    stats = get_question_bank_stats()
    print("Questions banque :", stats["total"])
    print("Domaines :")
    for domain in list_bank_domains():
        print("-", domain)


if __name__ == "__main__":
    main()
