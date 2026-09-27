"""Try the same assistant pipeline without a webcam; no action runs by default."""
import argparse
import json
from pathlib import Path

from assistant_core import Assistant


def main():
    parser = argparse.ArgumentParser(description="Inspect an eye assistant command without executing it")
    parser.add_argument("words", nargs="+", help='example: open youtube and play Shape of You')
    parser.add_argument("--execute", action="store_true",
                        help="run an approved browser action or open an email in Gmail; never SMTP send")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assistant = Assistant(config, root)
    plan = assistant.prepare(" ".join(args.words))
    print("ACTION:", plan.action)
    print("REVIEW:", plan.summary)
    if plan.details:
        print(plan.details)
    if plan.missing:
        print("NEED:", plan.missing)
    if args.execute and plan.ready:
        print("RESULT:", assistant.execute(plan))


if __name__ == "__main__":
    main()
