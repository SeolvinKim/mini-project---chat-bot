"""OpenAI TTS 음성들을 같은 한국어 문장으로 합성해 비교용 mp3로 저장한다.

실행:
    uv run python scripts/tts_try_voices.py
    uv run python scripts/tts_try_voices.py "원하는 문장을 직접 넣어도 됩니다."

필요:
    .env 에 OPENAI_API_KEY

결과:
    out/tts/openai-<voice>.mp3 로 저장된다. 다 들어보고 마음에 드는 음성을
    .env 의 TTS_VOICE 에 넣으면 /api/tts 의 기본 음성이 된다.
    말투는 .env 의 OPENAI_TTS_INSTRUCTIONS 로 조절한다(gpt-4o-mini-tts 기준).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import (
    OPENAI_TTS_INSTRUCTIONS,
    OPENAI_TTS_MODEL,
    OPENAI_VOICES,
    openai_tts,
)

SAMPLE = "안녕하세요. 오늘은 조금 특별한 이야기를 들려드릴게요."


def main() -> None:
    import os

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 가 .env 에 설정돼 있지 않습니다.")
        raise SystemExit(1)

    text = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    out_dir = ROOT / "out" / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'문장: "{text}"')
    print(f"모델: {OPENAI_TTS_MODEL}")
    print(f"말투: {OPENAI_TTS_INSTRUCTIONS or '(기본)'}\n")

    ok = 0
    for voice in sorted(OPENAI_VOICES):
        try:
            audio = openai_tts(text, voice)
        except Exception as error:
            print(f"  [x]  {voice}: {str(error)[:100]}")
            continue
        path = out_dir / f"openai-{voice}.mp3"
        path.write_bytes(audio)
        ok += 1
        print(f"  [ok] {voice:8s} -> {path.relative_to(ROOT)}  ({len(audio):,} bytes)")

    print(f"\n{ok}/{len(OPENAI_VOICES)} 음성 생성 완료. 폴더: {out_dir}")


if __name__ == "__main__":
    main()
