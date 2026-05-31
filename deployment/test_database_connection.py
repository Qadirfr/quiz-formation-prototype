from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.db_runtime import test_connection  # noqa: E402


def main() -> None:
    print("Test de connexion base de données")
    print("--------------------------------")
    try:
        result = test_connection()
    except Exception as exc:
        print("ECHEC")
        print(str(exc))
        raise SystemExit(1)
    print("OK")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
