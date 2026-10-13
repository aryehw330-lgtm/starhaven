#!/usr/bin/env python3
"""Build a vertical Starhaven daily episode from a story pack.

Usage:
  python3 make_episode.py PACK.json NARRATION_DIR OUT.mp4 [--title "Episode title"]

NARRATION_DIR must hold:
  intro.mp3        spoken over the title card (optional)
  clip1.mp3 ...    one narration file per clip, same order as pack["clips"]
  outro.mp3        spoken over the end card (optional)
Clip video files are looked up next to PACK.json by the names in pack["clips"][i]["file"].
"""
import json, os, subprocess, sys, tempfile, shutil

FONT = next((f for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                         "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                         "C:/Windows/Fonts/arialbd.ttf"] if os.path.exists(f)), None)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr[-2000:]); raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:6])}...")

def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")

def card(out, lines, seconds, narr=None):
    """Solid dark card with centered text lines [(text,size,color)], optional narration."""
    seconds = max(seconds, (dur(narr) + 0.8) if narr else 0)
    vf = []
    y = 520
    for text, size, color in lines:
        if FONT:
            vf.append(f"drawtext=fontfile='{FONT}':text='{esc(text)}':fontsize={size}:fontcolor={color}:x=(w-text_w)/2:y={y}")
        y += int(size * 1.5)
    vf = ",".join(vf) or "null"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x070914:s=720x1280:r=30:d={seconds:.2f}"]
    if narr:
        cmd += ["-i", narr, "-filter_complex", f"[0:v]{vf}[v];[1:a]adelay=300|300,apad,atrim=0:{seconds:.2f},aresample=48000[a]", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={seconds:.2f}", "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
    cmd += ["-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", out]
    run(cmd)

def segment(clip, narr, out):
    """Clip with its music ducked under narration; holds the last frame if the narration runs long."""
    cd = dur(clip) or 13.0
    nd = dur(narr) if narr and os.path.exists(narr) else 0
    total = max(cd, nd + 1.0)
    has_audio = bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", clip], capture_output=True, text=True).stdout.strip())
    cmd = ["ffmpeg", "-y", "-i", clip]
    v = f"[0:v]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=30,tpad=stop_mode=clone:stop_duration={max(0, total - cd) + 0.1:.2f},trim=0:{total:.2f},setpts=PTS-STARTPTS[v]"
    music = f"[0:a]volume=0.18,apad,atrim=0:{total:.2f},aresample=48000[m]" if has_audio else f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.2f}[m]"
    if nd:
        cmd += ["-i", narr]
        a = f"{music};[1:a]adelay=300|300,volume=1.5,apad,atrim=0:{total:.2f},aresample=48000[n];[m][n]amix=inputs=2:duration=first:normalize=0[a]"
    else:
        a = music.replace("[m]", "[a]")
    cmd += ["-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", out]
    run(cmd)

def main():
    args = sys.argv[1:]
    title = None
    if "--title" in args:
        i = args.index("--title"); title = args[i + 1]; del args[i:i + 2]
    pack_path, narr_dir, out = args
    pack = json.load(open(pack_path))
    base = os.path.dirname(os.path.abspath(pack_path))
    tmp = tempfile.mkdtemp()
    parts = []
    nd = lambda n: (os.path.join(narr_dir, n) if os.path.exists(os.path.join(narr_dir, n)) else None)
    card(os.path.join(tmp, "00.mp4"), [("STARHAVEN", 84, "0xffd35a"), (title or f"Day {pack.get('gameDay')} · {pack.get('age')}", 40, "0xece9f4"),
                                       ("nobody controls them", 30, "0x9aa1bf")], 3.5, nd("intro.mp3"))
    parts.append(os.path.join(tmp, "00.mp4"))
    for i, c in enumerate(pack.get("clips", []), 1):
        src = os.path.join(base, c["file"])
        if not os.path.exists(src):
            print("missing clip, skipping:", src); continue
        o = os.path.join(tmp, f"{i:02d}.mp4"); segment(src, nd(f"clip{i}.mp3"), o); parts.append(o)
    card(os.path.join(tmp, "99.mp4"), [("TALK TO THEM LIVE", 56, "0xffd35a"), ("type  !talk NAME hello", 38, "0x62c6b2"),
                                       ("in the live chat", 34, "0xece9f4"), ("Link below. Subscribe to see what happens.", 28, "0x9aa1bf")], 4.0, nd("outro.mp3"))
    parts.append(os.path.join(tmp, "99.mp4"))
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"done: {out} ({dur(out):.1f}s)")

if __name__ == "__main__":
    main()
