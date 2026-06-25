"""한국 여성 음성 5종을 같은 문장으로 합성해 비교용 mp3로 저장한다.

실행:
    uv run python scripts/tts_try_voices.py
    uv run python scripts/tts_try_voices.py "원하는 문장을 직접 넣어도 됩니다."

필요:
    .env 에 AZURE_SPEECH_KEY, AZURE_SPEECH_REGION (Azure Portal > Speech service)

결과:
    out/tts/<voice>.mp3 로 저장된다. 다 들어보고 마음에 드는 음성을
    .env 의 AZURE_TTS_VOICE 에 넣으면 /api/tts 의 기본 음성이 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_TTS_PITCH,
    AZURE_TTS_RATE,
    KO_FEMALE_VOICES,
    azure_tts,
)

SAMPLE = "안녕하세요. 오늘은 조금 특별한 이야기를 들려드릴게요."


def main() -> None:
    if not (AZURE_SPEECH_KEY and AZURE_SPEECH_REGION):
        print("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION 가 .env 에 설정돼 있지 않습니다.")
        print("Azure Portal 에서 'Speech service' 리소스를 만들고 키와 region 을 채워주세요.")
        raise SystemExit(1)

    text = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    out_dir = ROOT / "out" / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'문장: "{text}"')
    print(f"region={AZURE_SPEECH_REGION}  rate={AZURE_TTS_RATE}  pitch={AZURE_TTS_PITCH}\n")

    ok = 0
    for voice in KO_FEMALE_VOICES:
        try:
            audio = azure_tts(text, voice)
        except Exception as error:
            print(f"  ✗ {voice}: {error}")
            continue
        path = out_dir / f"{voice}.mp3"
        path.write_bytes(audio)
        ok += 1
        print(f"  ✓ {voice}  →  {path.relative_to(ROOT)}  ({len(audio):,} bytes)")

    print(f"\n{ok}/{len(KO_FEMALE_VOICES)} 음성 생성 완료. 폴더: {out_dir}")


if __name__ == "__main__":
    main()
