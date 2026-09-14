from PIL import Image
from pathlib import Path

src = Path(r"C:\Users\ahmad\.cursor\projects\d-Office-Work-Side-work-NexivoReach\assets")
dst = Path(r"d:\Office Work\Side work\NexivoReach\frontend\public\brand")
dst.mkdir(parents=True, exist_ok=True)

files = {
    "empty-queue.png": ("empty-queue.webp", 960),
    "empty-outreach.png": ("empty-outreach.webp", 960),
    "empty-activity.png": ("empty-activity.webp", 960),
    "empty-notifications.png": ("empty-notifications.webp", 720),
    "empty-support.png": ("empty-support.webp", 960),
    "login-atmosphere.png": ("login-atmosphere.webp", 1600),
    "suspended-atmosphere.png": ("suspended-atmosphere.webp", 1600),
    "splash-mark.png": ("splash-mark.webp", 512),
}

for src_name, (out_name, max_w) in files.items():
    p = src / src_name
    if not p.exists():
        print("missing", p)
        continue
    im = Image.open(p).convert("RGB")
    w, h = im.size
    if w > max_w:
        nh = int(h * max_w / w)
        im = im.resize((max_w, nh), Image.Resampling.LANCZOS)
    out = dst / out_name
    im.save(out, "WEBP", quality=78, method=6)
    print(out_name, out.stat().st_size, im.size)
