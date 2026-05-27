"""Smoke test: render a WordleHandle image with the requested 4 guesses for review."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from games.wordle_handle import WordleHandle  # noqa: E402

IDIOMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "chinese_idiom",
    "chengyu.json",
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_smoke_handle.png",
)

ANSWER = "痴人说梦"
GUESSES = ["荒无人烟", "杞人忧天", "痴心妄想", "痴人说梦"]


async def main() -> None:
    with open(IDIOMS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    idioms = {x["name"]: x["pinyin"] for x in data}

    missing = [w for w in [ANSWER, *GUESSES] if w not in idioms]
    if missing:
        raise SystemExit(f"以下成语不在词库: {missing}")

    game = WordleHandle(ANSWER, idioms)
    for g in GUESSES:
        png = await game.guess(g)
    try:
        with open(OUTPUT_PATH, "wb") as f:
            f.write(png)
        print(f"saved {OUTPUT_PATH} ({len(png)} bytes)")
    except Exception as e:
        raise SystemExit(f"保存图片失败: {e!s}")


if __name__ == "__main__":
    asyncio.run(main())
