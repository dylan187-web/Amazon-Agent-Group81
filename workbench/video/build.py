"""把 record.py 抓的帧 + 逐句配音合成 mp4。"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Desktop/第81组演示.mp4")
tl = json.load(open(os.path.join(HERE, "timeline.json")))
order = [lid for lid, _ in json.load(open(os.path.join(HERE, "lines.json")))]
shift = tl["first_frame_offset"]          # 视频从第一帧开始，配音跟着前移
total = tl["total"] - shift

# 1. 配音：每句按实际开始时间 adelay 后混音
inputs, filters = [], []
for i, lid in enumerate(order):
    inputs += ["-i", os.path.join(HERE, "tts", f"{lid}.mp3")]
    ms = max(0, int((tl["timeline"][lid] - shift) * 1000))
    filters.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
mix = "".join(f"[a{i}]" for i in range(len(order)))
filters.append(f"{mix}amix=inputs={len(order)}:normalize=0,apad,atrim=0:{total:.3f},loudnorm=I=-16:TP=-1.5[aout]")
audio = os.path.join(HERE, "voice.m4a")
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                "-filter_complex", ";".join(filters), "-map", "[aout]", "-c:a", "aac", "-b:a", "160k", audio], check=True)

# 2. 画面：帧清单 → 30fps 恒定帧率，与配音合并
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", os.path.join(HERE, "frames.txt"), "-i", audio,
                "-vf", "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-c:a", "copy",
                "-t", f"{total:.3f}", "-movflags", "+faststart", OUT], check=True)

d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", OUT],
                   capture_output=True, text=True).stdout
print(OUT, d)
