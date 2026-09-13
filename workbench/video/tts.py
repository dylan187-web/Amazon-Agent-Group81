"""逐句合成配音：lines.json → tts/<句子id>.mp3，并写 durations.json（每句秒数）。

依赖 edge-tts（微软神经网络语音，需联网，不需要 key）：
  python3 -m venv .venv && .venv/bin/pip install edge-tts playwright
"""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE = "zh-CN-YunxiNeural"
RATE = "+6%"
EDGE = shutil.which("edge-tts") or os.path.join(HERE, ".venv", "bin", "edge-tts")


def gen(item):
    lid, text = item
    out = os.path.join(HERE, "tts", f"{lid}.mp3")
    for _ in range(3):  # 网络偶发失败时重试
        if subprocess.run([EDGE, "--voice", VOICE, f"--rate={RATE}", "--text", text, "--write-media", out],
                          capture_output=True).returncode == 0:
            break
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.strip()
    return lid, float(probe or 0)


def main():
    os.makedirs(os.path.join(HERE, "tts"), exist_ok=True)
    lines = json.load(open(os.path.join(HERE, "lines.json"), encoding="utf-8"))
    with cf.ThreadPoolExecutor(4) as ex:
        durations = dict(ex.map(gen, lines))
    json.dump(durations, open(os.path.join(HERE, "durations.json"), "w"), indent=1)
    missing = [k for k, v in durations.items() if not v]
    print(f"{len(durations)} 句，缺失 {missing or '无'}，语音总长 {sum(durations.values()):.1f} 秒")


if __name__ == "__main__":
    main()
