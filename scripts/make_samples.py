"""Generates the demo inputs in samples/ (synthetic, no proprietary data).

  inspection_report_E204.png / .pdf  - a scanned-looking inspection report
  pid_crude_preheat.png              - a simple P&ID-style drawing
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workbench.config import SAMPLES_DIR  # noqa: E402


def font(size, bold=False):
    for name in (("arialbd.ttf", "calibrib.ttf") if bold else ("arial.ttf", "calibri.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


REPORT_LINES = [
    ("h", "COASTAL REFINERY UNIT"),
    ("h2", "EQUIPMENT INSPECTION REPORT"),
    ("gap", ""),
    ("kv", "Report No: IR/CDU/2026/0417          Date of Inspection: 28 September 2026"),
    ("kv", "Equipment: Heat Exchanger E-204 (Crude Preheat Train, CDU-1)"),
    ("kv", "Type: Shell and Tube, 420 tubes      Design Pressure: 14.0 kg/cm2"),
    ("kv", "Inspected by: R. Menon, Senior Inspection Engineer"),
    ("gap", ""),
    ("b", "FINDINGS"),
    ("p", "1. Shell thickness: nominal 12.0 mm. Minimum measured 9.2 mm at CML-07."),
    ("p", "   Minimum required thickness as per data sheet is 8.5 mm."),
    ("p", "2. Tube bundle: 14 of 420 tubes found leaking and plugged (3.3 percent)."),
    ("p", "3. Channel head flange gasket found leaking and hardened."),
    ("p", "4. Corrosion under insulation at nozzle N3: pitting up to 0.6 mm deep."),
    ("p", "5. Hydrostatic test at 18.2 kg/cm2 held for 30 minutes. No pressure drop,"),
    ("p", "   no visible leak. Test passed."),
    ("gap", ""),
    ("b", "RECOMMENDATION"),
    ("p", "Replace channel head gasket. Clean, recoat and re-insulate nozzle N3."),
    ("p", "Exchanger may be returned to service after the above repairs."),
    ("p", "Estimated repair cost: Rs 4.8 lakh (budget head: CDU-1 maintenance)."),
    ("gap", ""),
    ("p", "Signature: R. Menon                         Reviewed: S. Kulkarni, Manager (Inspection)"),
]


def make_report():
    w, h = 1240, 1754  # A4 at 150 dpi
    img = Image.new("RGB", (w, h), (252, 251, 247))
    d = ImageDraw.Draw(img)
    y = 110
    for kind, text in REPORT_LINES:
        if kind == "h":
            d.text((w // 2, y), text, font=font(40, True), fill=(20, 20, 20), anchor="ma")
            y += 62
        elif kind == "h2":
            d.text((w // 2, y), text, font=font(30, True), fill=(20, 20, 20), anchor="ma")
            y += 52
            d.line((90, y, w - 90, y), fill=(40, 40, 40), width=3)
            y += 18
        elif kind == "b":
            d.text((100, y), text, font=font(27, True), fill=(20, 20, 20))
            y += 48
        elif kind == "gap":
            y += 26
        else:
            d.text((100, y), text, font=font(25), fill=(30, 30, 30))
            y += 44
    d.rectangle((60, 60, w - 60, h - 60), outline=(60, 60, 60), width=2)
    d.text((w - 330, h - 130), "INSPECTION DEPT", font=font(24, True), fill=(150, 40, 40))
    d.rectangle((w - 350, h - 145, w - 95, h - 92), outline=(150, 40, 40), width=3)

    # make it look scanned: slight skew, soft focus, speckle noise
    img = img.rotate(0.5, resample=Image.BICUBIC, fillcolor=(252, 251, 247))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    rnd = random.Random(7)
    for _ in range(9000):
        x, yy = rnd.randrange(w), rnd.randrange(h)
        g = rnd.randrange(150, 215)
        px[x, yy] = (g, g, g)
    img.save(SAMPLES_DIR / "inspection_report_E204.png")
    img.save(SAMPLES_DIR / "inspection_report_E204.pdf", "PDF", resolution=150.0)


def make_pid():
    w, h = 1400, 800
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    black, f, fb = (15, 15, 15), font(22), font(24, True)

    def arrow(x1, y1, x2, y2):
        d.line((x1, y1, x2, y2), fill=black, width=4)
        if x2 > x1:
            d.polygon([(x2, y2), (x2 - 16, y2 - 9), (x2 - 16, y2 + 9)], fill=black)
        elif y2 < y1:
            d.polygon([(x2, y2), (x2 - 9, y2 + 16), (x2 + 9, y2 + 16)], fill=black)
        elif y2 > y1:
            d.polygon([(x2, y2), (x2 - 9, y2 - 16), (x2 + 9, y2 - 16)], fill=black)

    def bubble(x, y, tag):
        d.ellipse((x - 52, y - 38, x + 52, y + 38), outline=black, width=3, fill="white")
        d.text((x, y), tag, font=font(22, True), fill=black, anchor="mm")

    d.text((w // 2, 40), "P&ID - CRUDE PREHEAT SECTION (SAMPLE)", font=font(30, True), fill=black, anchor="ma")

    # storage tank
    d.rectangle((90, 300, 250, 560), outline=black, width=4)
    d.arc((90, 260, 250, 340), 180, 360, fill=black, width=4)
    d.text((170, 420), "T-101", font=fb, fill=black, anchor="mm")
    d.text((170, 590), "Crude Storage Tank", font=f, fill=black, anchor="ma")

    # pump
    arrow(250, 520, 380, 520)
    d.ellipse((380, 475, 470, 565), outline=black, width=4)
    d.polygon([(400, 495), (400, 545), (455, 520)], outline=black)
    d.text((425, 590), "P-101", font=fb, fill=black, anchor="ma")
    d.text((425, 620), "Feed Pump", font=f, fill=black, anchor="ma")

    # control valve
    arrow(470, 520, 600, 520)
    d.polygon([(600, 495), (600, 545), (660, 495), (660, 545)], outline=black, width=4)
    d.line((630, 520, 630, 470), fill=black, width=3)
    d.arc((605, 440, 655, 490), 180, 360, fill=black, width=3)
    d.text((630, 560), "FCV-101", font=fb, fill=black, anchor="ma")
    bubble(630, 380, "FT-101")
    d.line((630, 418, 630, 440), fill=black, width=2)

    # heat exchanger
    arrow(660, 520, 800, 520)
    d.rounded_rectangle((800, 470, 1040, 570), radius=45, outline=black, width=4)
    for x in range(840, 1010, 34):
        d.line((x, 480, x, 560), fill=black, width=2)
    d.text((975, 590), "E-204", font=fb, fill=black, anchor="ma")
    d.text((975, 620), "Crude Preheat Exchanger", font=f, fill=black, anchor="ma")
    arrow(830, 300, 830, 470)   # kept clear of the captions so no line runs through the text
    d.text((845, 300), "Hot Diesel In", font=f, fill=black)
    arrow(830, 570, 830, 720)
    d.text((845, 695), "Diesel Out", font=f, fill=black)
    bubble(1010, 380, "TT-103")
    d.line((1010, 418, 1010, 470), fill=black, width=2)

    # to column
    arrow(1040, 520, 1200, 520)
    bubble(1120, 430, "PT-102")
    d.line((1120, 468, 1120, 520), fill=black, width=2)
    d.rectangle((1200, 200, 1300, 640), outline=black, width=4)
    d.text((1250, 420), "C-101", font=fb, fill=black, anchor="mm")
    d.text((1250, 655), "Distillation", font=f, fill=black, anchor="ma")
    d.text((1250, 682), "Column", font=f, fill=black, anchor="ma")

    d.rectangle((20, 20, w - 20, h - 20), outline=black, width=2)
    d.text((40, h - 60), "DRG No: PID-CDU1-0042   REV 2   NOT TO SCALE", font=font(20), fill=black)
    img.save(SAMPLES_DIR / "pid_crude_preheat.png")


if __name__ == "__main__":
    make_report()
    make_pid()
    for p in sorted(SAMPLES_DIR.iterdir()):
        print("created", p.name, f"{p.stat().st_size // 1024} KB")
