"""A polished synthetic checkout screen, shared by the screenshot tools.

One renderer drives both the heatmap background and the viewer-demo video, and
exports the interactive element positions so the synthetic session's movement
clusters land exactly on the fields the screen draws. Nothing here ships in the
package — it only exists to make the README visuals look like a real capture.
"""

from PIL import Image, ImageDraw

W, H = 1440, 810

# Brand-ish dark palette.
BG = "#0a0e16"
CARD = "#121a28"
CARD_BORDER = "#202b3d"
FIELD = "#0d141f"
FIELD_BORDER = "#283449"
FOCUS = "#22d3ee"
TEXT = "#e6eaf2"
MUTED = "#7c8aa0"
LABEL = "#9aa7bd"
ACCENT_A = (37, 99, 235)    # blue
ACCENT_B = (6, 182, 212)    # cyan
RAGE = "#f87171"

# Interactive elements. ``box`` is (x0, y0, x1, y1); ``weight`` scales how much
# the pointer dwells there (and so how hot the heatmap runs). The session
# generator and the heatmap/video all read this one layout.
ELEMENTS = [
    {"id": "email",   "label": "Email",        "box": (120, 196, 740, 252), "weight": 1.0, "kind": "field"},
    {"id": "card",    "label": "Card number",  "box": (120, 300, 740, 356), "weight": 1.1, "kind": "field"},
    {"id": "exp",     "label": "Expiry",       "box": (120, 404, 420, 460), "weight": 0.7, "kind": "field"},
    {"id": "cvc",     "label": "CVC",          "box": (440, 404, 740, 460), "weight": 0.8, "kind": "field"},
    {"id": "summary", "label": "Order total",  "box": (840, 470, 1330, 536), "weight": 0.9, "kind": "review"},
    {"id": "pay",     "label": "Pay $129.00",  "box": (120, 600, 740, 678), "weight": 2.2, "kind": "cta"},
]


def hotspots():
    """(cx, cy, weight, kind, id) per interactive element — for the generator."""
    out = []
    for e in ELEMENTS:
        x0, y0, x1, y1 = e["box"]
        out.append(((x0 + x1) // 2, (y0 + y1) // 2, e["weight"], e["kind"], e["id"]))
    return out


def _font(size, bold=False):
    from matplotlib.font_manager import FontProperties, findfont
    from PIL import ImageFont
    return ImageFont.truetype(findfont(FontProperties(
        family="DejaVu Sans", weight="bold" if bold else "normal")), size)


def _gradient(draw, box, c0, c1, radius=12):
    x0, y0, x1, y1 = box
    w = int(x1 - x0)
    strip = Image.new("RGB", (w, 1))
    for i in range(w):
        f = i / max(1, w - 1)
        strip.putpixel((i, 0), tuple(int(a + (b - a) * f) for a, b in zip(c0, c1)))
    strip = strip.resize((w, int(y1 - y0)))
    mask = Image.new("L", strip.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, int(y1 - y0) - 1),
                                           radius=radius, fill=255)
    draw._image.paste(strip, (int(x0), int(y0)), mask)


def render_screen(cursor=None, paid=False):
    """Render the checkout screen. ``cursor`` is (x, y) in screen space; the
    element nearest the cursor is drawn focused."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d._image = img  # for _gradient paste

    f_logo, f_h2, f_lbl = _font(26, bold=True), _font(21, bold=True), _font(16)
    f_val, f_big, f_btn = _font(20), _font(30, bold=True), _font(22, bold=True)

    # top bar
    d.line((0, 70, W, 70), fill=CARD_BORDER)
    d.ellipse((40, 28, 60, 48), fill=ACCENT_B)
    d.text((72, 30), "Lumen", font=f_logo, fill=TEXT)
    d.text((175, 35), "Checkout", font=f_lbl, fill=MUTED)
    d.text((W - 215, 34), "Secure payment", font=f_lbl, fill=MUTED)
    d.ellipse((W - 240, 38, W - 226, 52), outline="#3b82f6", width=2)

    # which element is focused
    active = None
    if cursor:
        best = 1e9
        for e in ELEMENTS:
            x0, y0, x1, y1 = e["box"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            dist = (cursor[0] - cx) ** 2 + (cursor[1] - cy) ** 2
            if dist < best and dist < 150 ** 2:
                best, active = dist, e["id"]

    # payment card
    d.rounded_rectangle((90, 108, 770, 718), radius=16, fill=CARD, outline=CARD_BORDER, width=2)
    d.text((120, 132), "Payment details", font=f_h2, fill=TEXT)

    placeholders = {
        "email": "jordan@lumen.io", "card": "4242  4242  4242  4242",
        "exp": "04 / 27", "cvc": "•••",
    }
    for e in ELEMENTS:
        if e["kind"] not in ("field",):
            continue
        x0, y0, x1, y1 = e["box"]
        focused = e["id"] == active
        d.text((x0, y0 - 24), e["label"], font=f_lbl, fill=LABEL)
        d.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=FIELD,
                            outline=FOCUS if focused else FIELD_BORDER,
                            width=2 if focused else 1)
        d.text((x0 + 18, y0 + 16), placeholders.get(e["id"], ""), font=f_val,
               fill=TEXT if focused else MUTED)
        if focused:  # caret
            d.line((x0 + 18, y0 + 14, x0 + 18, y1 - 14), fill=FOCUS, width=2)

    # pay button (gradient)
    pay = next(e for e in ELEMENTS if e["id"] == "pay")
    _gradient(d, pay["box"], ACCENT_A, ACCENT_B, radius=12)
    if active == "pay":
        d.rounded_rectangle(pay["box"], radius=12, outline=FOCUS, width=3)
    label = "✓ Paid" if paid else "Pay $129.00"
    bb = d.textbbox((0, 0), label, font=f_btn)
    px = (pay["box"][0] + pay["box"][2]) / 2 - (bb[2] - bb[0]) / 2
    d.text((px, pay["box"][1] + 24), label, font=f_btn, fill="#ffffff")

    # order summary card
    d.rounded_rectangle((820, 108, 1350, 560), radius=16, fill=CARD, outline=CARD_BORDER, width=2)
    d.text((852, 132), "Order summary", font=f_h2, fill=TEXT)
    items = [("Aurora Wireless Headphones", "$99.00"), ("USB-C Braided Cable", "$12.00"),
             ("Express shipping", "$18.00")]
    y = 192
    for nm, price in items:
        d.rounded_rectangle((852, y, 892, y + 40), radius=8, fill="#1b2536")
        d.text((908, y + 8), nm, font=f_lbl, fill=TEXT)
        d.text((1270, y + 8), price, font=f_lbl, fill=MUTED)
        y += 58
    d.line((852, 452, 1318, 452), fill=CARD_BORDER)
    if active == "summary":
        d.rounded_rectangle((836, 466, 1334, 540), radius=10, outline=FOCUS, width=2)
    d.text((852, 484), "Total", font=f_lbl, fill=LABEL)
    d.text((1212, 476), "$129.00", font=f_big, fill=TEXT)

    if cursor:
        cx, cy = cursor
        d.polygon([(cx, cy), (cx, cy + 22), (cx + 6, cy + 16), (cx + 11, cy + 26),
                   (cx + 15, cy + 24), (cx + 10, cy + 14), (cx + 18, cy + 14)],
                  fill="#ffffff", outline="#0a0e16")
    return img


if __name__ == "__main__":  # quick visual check
    render_screen(cursor=(430, 333)).save("/tmp/mock_screen.png")
    print("wrote /tmp/mock_screen.png")
