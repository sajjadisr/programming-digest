"""Local dry-run helper.

Usage:
    python scripts/run_local.py sourcing      # just fetch + print candidate counts
    python scripts/run_local.py score         # sourcing + mechanical score/filter
    python scripts/run_local.py select        # + LLM select/cluster (costs tokens)
    python scripts/run_local.py full          # the entire pipeline, including sending to Telegram
    python scripts/run_local.py picks         # poll Telegram once for pick/reject taps

Loads .env if present (put TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / GEMINI_API_KEY /
GROQ_API_KEY there).
Does NOT commit anything to git - that only happens in the GitHub Actions workflows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _load_dotenv() -> None:
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def main() -> None:
    _load_dotenv()
    mode = sys.argv[1] if len(sys.argv) > 1 else "score"

    from score import filter_seen, score_and_cut
    from sourcing import collect_all
    from utils import SEEN_LINKS_PATH, load_feeds_config, load_json

    config = load_feeds_config()

    if mode == "sourcing":
        items = collect_all(config)
        print(f"{len(items)} raw candidates")
        for it in items[:10]:
            print(f"  [{it['tier']}] {it['source']:20s} {it['title'][:70]}")
        return

    if mode in ("score", "select"):
        seen = set(load_json(SEEN_LINKS_PATH, []))
        items = collect_all(config)
        fresh = filter_seen(items, seen)
        scored = score_and_cut(fresh, config["scoring"])
        print(f"{len(scored)} candidates pass mechanical score/filter:")
        for it in scored[:20]:
            print(f"  {it['mech_score']:5.2f}  {it['source']:20s} {it['title'][:70]}")

        if mode == "select":
            from select_llm import select_and_cluster
            worthy = select_and_cluster(scored)
            print(f"\n{len(worthy)} clusters judged worthy:")
            for c in worthy:
                print(f"  {c['title'][:70]}  <- {c['select_reason']}")
        return

    if mode == "full":
        import propose
        propose.main()
        return

    if mode == "picks":
        import collect_picks
        collect_picks.main()
        return

    print(f"Unknown mode: {mode}")
    sys.exit(1)


if __name__ == "__main__":
    main()
