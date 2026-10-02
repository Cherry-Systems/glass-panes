#!/usr/bin/env python3
"""Draws all Glass Panes artwork from code (no third-party images).

  make-artwork.py OUT_DIR

Writes:
  logo.png, logo-<size>.png         the Glass Panes mark (two overlapping glass panes)
  logo-mono.png                     white mark, for dark surfaces
  user.png                          default account picture
  wallpapers/*.png                  original desktop backgrounds (light and dark)
  grub.png                          live ISO boot menu background (1024x768)
  plymouth/logo.png, dot.png        boot screen pieces (the dots spin in the Plymouth script)
  sddm/background.png, user.png     sign-in screen
  welcome.png, slide*.png           installer artwork
"""
import math
import os
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELAWIK_ZIP = os.path.join(ROOT, "build", "cache", "ext", "selawik.zip")

ACCENT = (0, 103, 192)


def font(size, weight="regular"):
    names = {"regular": "selawk.ttf", "semibold": "selawksb.ttf", "light": "selawkl.ttf",
             "semilight": "selawksl.ttf", "bold": "selawkb.ttf"}
    if os.path.exists(SELAWIK_ZIP):
        cache = os.path.join(ROOT, "build", "cache", "fonts")
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, names[weight])
        if not os.path.exists(path):
            with zipfile.ZipFile(SELAWIK_ZIP) as z:
                with open(path, "wb") as f:
                    f.write(z.read(names[weight]))
        return ImageFont.truetype(path, size)
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def linear_gradient(size, top_left, bottom_right, angle_deg=135):
    """RGB gradient image across `size` along `angle_deg`."""
    w, h = size
    a = math.radians(angle_deg)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    proj = (xx / w) * math.cos(a - math.pi / 2) * -1 + (yy / h) * math.sin(a)
    proj = (proj - proj.min()) / (proj.max() - proj.min() + 1e-6)
    c0 = np.array(top_left, np.float32)
    c1 = np.array(bottom_right, np.float32)
    img = c0[None, None, :] * (1 - proj[..., None]) + c1[None, None, :] * proj[..., None]
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB")


def rounded_mask(size, box, radius, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([v * ss for v in box], radius * ss, fill=255)
    return m.resize(size, Image.LANCZOS)


# ----------------------------------------------------------------------------- logo

def draw_logo(size=512, mono=False):
    """Two overlapping rounded glass panes, the front one with a diagonal glare."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    back_box = (s * 0.30, s * 0.08, s * 0.92, s * 0.70)
    front_box = (s * 0.08, s * 0.30, s * 0.70, s * 0.92)
    r = s * 0.12

    # Back pane: lighter, slightly transparent.
    m = rounded_mask((s, s), back_box, r)
    fill = Image.new("RGBA", (s, s), (255, 255, 255, 255)) if mono else \
        linear_gradient((s, s), (126, 214, 255), (40, 150, 235)).convert("RGBA")
    alpha = m.point(lambda v: int(v * (0.55 if mono else 0.85)))
    fill.putalpha(alpha)
    img.alpha_composite(fill)

    # Soft shadow of the front pane onto the back pane.
    sh = rounded_mask((s, s), tuple(v + s * 0.02 for v in front_box), r).filter(
        ImageFilter.GaussianBlur(s * 0.03))
    shadow = Image.new("RGBA", (s, s), (0, 30, 80, 255))
    shadow.putalpha(sh.point(lambda v: int(v * (0.25 if not mono else 0.0))))
    img.alpha_composite(shadow)

    # Front pane.
    m = rounded_mask((s, s), front_box, r)
    fill = Image.new("RGBA", (s, s), (255, 255, 255, 255)) if mono else \
        linear_gradient((s, s), (24, 160, 251), (0, 84, 190)).convert("RGBA")
    fill.putalpha(m)
    img.alpha_composite(fill)

    # Diagonal glare stripe, clipped to the front pane.
    glare = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(glare)
    x0, y0, x1, y1 = front_box
    w = x1 - x0
    d.polygon([(x0 + w * 0.15, y1), (x0 + w * 0.42, y1), (x1, y0 + w * 0.42), (x1, y0 + w * 0.15)],
              fill=255)
    d.polygon([(x0 + w * 0.52, y1), (x0 + w * 0.60, y1), (x1, y0 + w * 0.60), (x1, y0 + w * 0.52)],
              fill=200)
    glare = Image.fromarray(np.minimum(np.array(glare), np.array(m)).astype(np.uint8))
    white = Image.new("RGBA", (s, s), (255, 255, 255, 255) if not mono else (0, 60, 140, 255))
    white.putalpha(glare.point(lambda v: int(v * (0.22 if not mono else 0.35))))
    img.alpha_composite(white)

    # Thin bright rim on the front pane's top-left edges.
    rim = Image.new("L", (s * 4, s * 4), 0)
    ImageDraw.Draw(rim).rounded_rectangle([v * 4 for v in front_box], r * 4,
                                          outline=255, width=max(4, int(s * 0.012 * 4)))
    rim = rim.resize((s, s), Image.LANCZOS)
    rimc = Image.new("RGBA", (s, s), (255, 255, 255, 255))
    rimc.putalpha(rim.point(lambda v: int(v * (0.45 if not mono else 0.0))))
    img.alpha_composite(rimc)
    return img


# ----------------------------------------------------------------------------- wallpaper

def bloom(size, dark):
    """A flower of translucent glass panes fanned out around a point, on a soft gradient."""
    W, H = size
    ss = 2
    w, h = W * ss, H * ss
    if dark:
        bg = linear_gradient((w, h), (6, 12, 28), (14, 38, 76), 120)
        petal_inner, petal_outer = (10, 60, 170), (90, 190, 255)
        glow_col = (30, 110, 230)
    else:
        bg = linear_gradient((w, h), (226, 236, 248), (176, 204, 238), 120)
        petal_inner, petal_outer = (0, 92, 210), (150, 220, 255)
        glow_col = (90, 160, 240)
    canvas = bg.convert("RGBA")
    cx, cy = w * 0.50, h * 0.74

    # Wide soft glow behind the flower.
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse([cx - w * 0.28, cy - h * 0.34, cx + w * 0.28, cy + h * 0.30], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
    gl = Image.new("RGBA", (w, h), glow_col + (255,))
    gl.putalpha(glow.point(lambda v: int(v * (0.55 if dark else 0.45))))
    canvas.alpha_composite(gl)

    def pane_outline(d0, length, width, radius, ang):
        """Rounded rectangle lying along direction `ang` (degrees), starting d0 from the centre."""
        pts = []
        u0, u1, v0, v1 = d0, d0 + length, -width / 2, width / 2
        corners = [(u1 - radius, v0 + radius, -90), (u1 - radius, v1 - radius, 0),
                   (u0 + radius, v1 - radius, 90), (u0 + radius, v0 + radius, 180)]
        for ccx, ccy, start in corners:
            for k in range(13):
                t = math.radians(start + k * 90 / 12)
                pts.append((ccx + radius * math.cos(t), ccy + radius * math.sin(t)))
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        return [(cx + u * ca - v * sa, cy + u * sa + v * ca) for u, v in pts]

    n = 8
    span = 150
    # Back row (long, faint) then the front row, shorter and offset by half a step.
    rows = [(0.50, 0.40, 0.0), (0.36, 0.62, span / (n - 1) / 2)]
    inner = np.array(petal_inner, np.float32)
    outer = np.array(petal_outer, np.float32)
    for reach, alpha, offset in rows:
        for i in range(n):
            t = i / (n - 1)
            ang = -90 - span / 2 + t * span + offset
            length = h * reach * (1.0 - abs(t - 0.5) * 0.35)
            width = h * 0.15 * (reach / 0.5) ** 0.5
            pts = pane_outline(h * 0.03, length, width, width * 0.32, ang)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bx0, by0 = max(int(min(xs)) - 4, 0), max(int(min(ys)) - 4, 0)
            bx1, by1 = min(int(max(xs)) + 4, w), min(int(max(ys)) + 4, h)
            if bx1 <= bx0 or by1 <= by0:
                continue
            bw, bh = bx1 - bx0, by1 - by0
            local = [(x - bx0, y - by0) for x, y in pts]
            mask = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(mask).polygon(local, fill=255)
            edge = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(edge).line(local + [local[0]], fill=255, width=ss * 2)
            yy, xx = np.mgrid[by0:by1, bx0:bx1].astype(np.float32)
            a = math.radians(ang)
            prog = (((xx - cx) * math.cos(a) + (yy - cy) * math.sin(a)) / (length + h * 0.03)).clip(0, 1)
            col = inner[None, None, :] * (1 - prog[..., None]) + outer[None, None, :] * prog[..., None]
            m = np.array(mask, np.float32) / 255.0
            fade = 0.55 + 0.45 * prog
            rgba = np.dstack([col, (m * fade * alpha * 255)]).clip(0, 255).astype(np.uint8)
            canvas.alpha_composite(Image.fromarray(rgba, "RGBA"), (bx0, by0))
            ec = Image.new("RGBA", (bw, bh), (255, 255, 255, 255))
            ec.putalpha(edge.point(lambda v: int(v * (0.30 if dark else 0.50))))
            canvas.alpha_composite(ec, (bx0, by0))

    # Bright core where the panes meet.
    core = Image.new("L", (w, h), 0)
    ImageDraw.Draw(core).ellipse([cx - h * 0.05, cy - h * 0.05, cx + h * 0.05, cy + h * 0.05], fill=255)
    core = core.filter(ImageFilter.GaussianBlur(h * 0.04))
    cc = Image.new("RGBA", (w, h), (220, 240, 255, 255))
    cc.putalpha(core.point(lambda v: int(v * 0.6)))
    canvas.alpha_composite(cc)
    return canvas.convert("RGB").resize((W, H), Image.LANCZOS)


def ribbons(size, dark):
    """Flowing translucent ribbons, a calmer second background."""
    W, H = size
    if dark:
        bg = linear_gradient((W, H), (8, 8, 24), (34, 16, 60), 160)
        cols = [(110, 70, 230), (40, 120, 240), (200, 80, 200)]
    else:
        bg = linear_gradient((W, H), (244, 240, 252), (214, 222, 248), 160)
        cols = [(150, 120, 250), (90, 160, 250), (240, 140, 220)]
    canvas = bg.convert("RGBA")
    xs = np.linspace(-0.1, 1.1, 600)
    for k, col in enumerate(cols):
        for j in range(18):
            phase = k * 1.7 + j * 0.035
            amp = 0.10 + 0.02 * k
            ys = 0.58 + 0.08 * k - 0.1 + amp * np.sin(xs * 3.0 + phase) + 0.05 * np.sin(xs * 7 + k)
            pts = [(x * W, y * H + j * 3.0) for x, y in zip(xs, ys)]
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(layer).line(pts, fill=col + (int(26 + 4 * math.sin(j)),), width=6)
            canvas.alpha_composite(layer)
    glow = canvas.filter(ImageFilter.GaussianBlur(18))
    out = Image.blend(canvas, glow, 0.5)
    return out.convert("RGB")


# ----------------------------------------------------------------------------- other art

def user_picture(size=256):
    """Windows-style default account picture: grey disc with a white person."""
    ss = 4
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, s - 1, s - 1], fill=(200, 205, 212, 255))
    person = Image.new("L", (s, s), 0)
    pd = ImageDraw.Draw(person)
    pd.ellipse([s * 0.34, s * 0.18, s * 0.66, s * 0.50], fill=255)
    pd.ellipse([s * 0.16, s * 0.56, s * 0.84, s * 1.20], fill=255)
    circle = Image.new("L", (s, s), 0)
    ImageDraw.Draw(circle).ellipse([0, 0, s - 1, s - 1], fill=255)
    person = Image.fromarray(np.minimum(np.array(person), np.array(circle)))
    white = Image.new("RGBA", (s, s), (255, 255, 255, 255))
    white.putalpha(person)
    img.alpha_composite(white)
    return img.resize((size, size), Image.LANCZOS)


def grub_background(logo):
    img = Image.new("RGB", (1024, 768), (0, 0, 0))
    lg = logo.resize((120, 120), Image.LANCZOS)
    img.paste(lg, (452, 90), lg)
    d = ImageDraw.Draw(img)
    f = font(34, "semilight")
    text = "Glass Panes"
    tw = d.textlength(text, font=f)
    d.text(((1024 - tw) / 2, 228), text, font=f, fill=(235, 235, 235))
    return img


def installer_slide(title, body, logo, wallpaper, size=(800, 440)):
    img = wallpaper.resize((size[0], int(wallpaper.height * size[0] / wallpaper.width)),
                           Image.LANCZOS).crop((0, 0) + size).convert("RGBA")
    panel = Image.new("RGBA", size, (255, 255, 255, 0))
    ImageDraw.Draw(panel).rounded_rectangle([40, 40, size[0] - 40, size[1] - 40], 16,
                                            fill=(255, 255, 255, 215))
    img.alpha_composite(panel)
    lg = logo.resize((72, 72), Image.LANCZOS)
    img.alpha_composite(lg, (72, 72))
    d = ImageDraw.Draw(img)
    d.text((168, 82), title, font=font(34, "semibold"), fill=(20, 20, 20))
    y = 180
    for line in body:
        d.text((72, y), line, font=font(22), fill=(50, 50, 50))
        y += 36
    return img.convert("RGB")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "build/art"
    for sub in ("", "wallpapers", "plymouth", "sddm"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    logo = draw_logo(1024)
    logo.resize((512, 512), Image.LANCZOS).save(os.path.join(out, "logo.png"))
    for px in (16, 24, 32, 48, 64, 128, 256):
        logo.resize((px, px), Image.LANCZOS).save(os.path.join(out, f"logo-{px}.png"))
    draw_logo(512, mono=True).save(os.path.join(out, "logo-mono.png"))
    user = user_picture(256)
    user.save(os.path.join(out, "user.png"))

    size = (2560, 1600)
    walls = {
        "glass-bloom-light": bloom(size, dark=False),
        "glass-bloom-dark": bloom(size, dark=True),
        "glass-flow-light": ribbons(size, dark=False),
        "glass-flow-dark": ribbons(size, dark=True),
    }
    for name, img in walls.items():
        img.save(os.path.join(out, "wallpapers", name + ".png"), optimize=True)

    grub_background(logo).save(os.path.join(out, "grub.png"))

    logo.resize((200, 200), Image.LANCZOS).save(os.path.join(out, "plymouth", "logo.png"))
    dot = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(dot).ellipse([2, 2, 61, 61], fill=(255, 255, 255, 255))
    dot.resize((12, 12), Image.LANCZOS).save(os.path.join(out, "plymouth", "dot.png"))

    sddm_bg = walls["glass-bloom-light"].resize((1920, 1200), Image.LANCZOS).convert("RGB")
    sddm_bg.save(os.path.join(out, "sddm", "background.png"))
    blurred = sddm_bg.resize((480, 300), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    blurred = Image.blend(blurred, Image.new("RGB", blurred.size, (20, 40, 70)), 0.28)
    blurred.resize((1920, 1200), Image.BICUBIC).save(os.path.join(out, "sddm", "background-blur.png"))
    user.save(os.path.join(out, "sddm", "user.png"))

    light = walls["glass-bloom-light"]
    installer_slide("Welcome to Glass Panes", [
        "Everything you know from Windows, without the bloat.",
        "Start, Settings, File Explorer and your Windows apps",
        "work just the way you expect.",
    ], logo, light).save(os.path.join(out, "welcome.png"))
    slides = [
        ("Your Windows apps", ["Download a .exe or .msi and double-click it.",
                               "It installs and appears in Start, just like on Windows."]),
        ("Fast and light", ["No adverts, no bloatware, no forced restarts.",
                            "Glass Panes runs well on older PCs too."]),
        ("Make it yours", ["Light or dark mode, accent colours and backgrounds",
                           "are all in Settings > Personalisation."]),
    ]
    for i, (title, body) in enumerate(slides, 1):
        installer_slide(title, body, logo, light).save(os.path.join(out, f"slide{i}.png"))
    print(f"Artwork written to {out}")


if __name__ == "__main__":
    main()
