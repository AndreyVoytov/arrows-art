from __future__ import annotations

import sys

from balance_pipeline import prepare_balance_local


def main(_argv: list[str] | None = None) -> None:
    prepare_balance_local()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as error:
        print(f"prepare-balance-local failed: {error}", file=sys.stderr)
        raise
