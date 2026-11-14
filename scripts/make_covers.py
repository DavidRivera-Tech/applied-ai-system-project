"""Generate fictional album covers for every song in data/songs.csv.

Each song gets its own made-up album: a cover drawn in code (no downloaded art,
no image API) in a style that matches the song's genre, plus the album title
and artist name. Covers are saved as assets/covers/<id>.png (e.g. 01.png), and
the app looks them up by song id.

Run from the project root:
    python scripts/make_covers.py
"""

import csv
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = ROOT / "data" / "songs.csv"
OUT_DIR = ROOT / "assets" / "covers"
SIZE = 600

# Fictional album title for each song id. All names are invented.
ALBUMS = {
    1: "City of Mornings",
    2: "Late Shift Tapes",
    3: "High Voltage Weather",
    4: "Quiet Stacks",
    5: "Rep Count",
    6: "Low Orbit",
    7: "Corner Table",
    8: "Afterhours FM",
    9: "Deep Work Sessions",
    10: "Rooftop Season",
    11: "Concrete Crown",
    12: "Pulse Theory",
    13: "Porch Light Stories",
    14: "Nocturnes for the Blue Hour",
    15: "Iron Cathedral",
    16: "Velvet Hours",
    17: "Island Time",
    18: "Willow Road",
    19: "Crossroads",
    20: "Fuego",
    21: "Afterglow",
    22: "Blue Smoke Sessions",
    23: "After Hours Quartet",
    24: "Static Hearts",
    25: "Interstate Nights",
    26: "Glass Lake",
    27: "Signal Garden",
    28: "Arcade Summer",
    29: "Laser Horizon",
    30: "Last Bus Home",
    31: "Paper Plane Parade",
    32: "Corner Office",
    33: "Cold Window Bars",
    34: "Tidal",
    35: "Overdrive Protocol",
    36: "Small Town Goodbye",
    37: "Gravel Road Letters",
    38: "Winter Elegies",
    39: "Morning Preludes",
    40: "Forge of Ashes",
    41: "Blackout Tempest",
    42: "Midnight Crown",
    43: "Almost Ours",
    44: "Sunset Riddim",
    45: "Old Kingston Radio",
    46: "Orchard Letters",
    47: "Campfire Morning",
    48: "Midnight Train",
    49: "Rolling Thunder",
    50: "Corazón de Fuego",
    51: "Noche de Tambores",
    52: "Ashes in the Wind",
    53: "Dawn Patrol",
    54: "Polaroid Summer",
    55: "Quiet Hours",
    56: "Velvet Sky",
    57: "Hometown Fireworks",
    58: "Rainy Bus Window",
    59: "Saltwater Goodbye",
    60: "Street Hype",
}

FONT_CANDIDATES = {
    "bold": ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"],
    "regular": ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"],
    "serif": ["DejaVuSerif-Bold.ttf", "georgiab.ttf", "timesbd.ttf", "LiberationSerif-Bold.ttf"],
}
FONT_DIRS = ["", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/",
             "C:/Windows/Fonts/", "/Library/Fonts/", "/System/Library/Fonts/Supplemental/"]


def font(kind: str, size: int):
    for name in FONT_CANDIDATES[kind]:
        for d in FONT_DIRS:
            try:
                return ImageFont.truetype(d + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- helpers

def gradient(c1, c2, vertical=True):
    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    for i in range(SIZE):
        t = i / (SIZE - 1)
        col = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
        for j in range(SIZE):
            if vertical:
                px[j, i] = col
            else:
                px[i, j] = col
    return img


def radial(center_col, edge_col, cx=0.5, cy=0.5):
    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    maxd = math.hypot(SIZE, SIZE) * 0.6
    for y in range(SIZE):
        for x in range(SIZE):
            t = min(1.0, math.hypot(x - cx * SIZE, y - cy * SIZE) / maxd)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(center_col, edge_col))
    return img


def glow(img, draw_fn, blur=18):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    blurred = layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(blurred, (0, 0), blurred)
    img.paste(layer, (0, 0), layer)


def grain(img, rng, amount=10):
    px = img.load()
    for _ in range(SIZE * SIZE // 6):
        x, y = rng.randrange(SIZE), rng.randrange(SIZE)
        r, g, b = px[x, y][:3]
        d = rng.randint(-amount, amount)
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))


# ---------------------------------------------------------------- genre styles
# Each returns an RGB image with artwork only; text is added afterwards.

def style_pop(rng, song):
    img = gradient((255, 140, 90), (255, 80, 150))
    d = ImageDraw.Draw(img)
    d.ellipse((150, 120, 450, 420), fill=(255, 220, 120))
    for i in range(6):
        y = 330 + i * 28
        d.rectangle((0, y, SIZE, y + 12), fill=(255, 120 + i * 10, 140))
    for _ in range(9):
        x = rng.randint(30, 570); h = rng.randint(120, 260)
        d.rectangle((x, SIZE - h, x + rng.randint(30, 60), SIZE), fill=(120, 40, 110))
    return img


def style_pop_romantic(rng, song):
    img = gradient((250, 170, 190), (120, 70, 160))
    def hearts(d):
        for _ in range(14):
            x, y, s = rng.randint(40, 560), rng.randint(60, 480), rng.randint(18, 50)
            d.ellipse((x - s, y - s // 2, x, y + s // 2), fill=(255, 220, 230, 170))
            d.ellipse((x, y - s // 2, x + s, y + s // 2), fill=(255, 220, 230, 170))
            d.polygon([(x - s, y), (x + s, y), (x, y + s + s // 2)], fill=(255, 220, 230, 170))
    glow(img, hearts, 8)
    return img


def style_lofi(rng, song):
    img = gradient((40, 50, 90), (110, 90, 140))
    d = ImageDraw.Draw(img)
    d.rectangle((120, 90, 480, 400), fill=(255, 205, 140))           # lit window
    d.line((300, 90, 300, 400), fill=(60, 50, 80), width=10)
    d.line((120, 245, 480, 245), fill=(60, 50, 80), width=10)
    d.rectangle((110, 80, 490, 410), outline=(60, 50, 80), width=14)
    for _ in range(70):                                               # rain
        x, y = rng.randint(0, SIZE), rng.randint(0, SIZE)
        d.line((x, y, x - 6, y + 26), fill=(170, 180, 230), width=2)
    d.rectangle((0, 430, SIZE, SIZE), fill=(55, 45, 70))              # desk
    d.ellipse((380, 360, 450, 440), fill=(230, 220, 210))             # mug
    return img


def style_rock(rng, song):
    img = gradient((25, 25, 35), (70, 20, 30))
    def bolt(d):
        pts = [(330, 40), (210, 300), (300, 300), (240, 560), (420, 240), (320, 240), (400, 40)]
        d.polygon(pts, fill=(255, 220, 60, 255))
    glow(img, bolt, 25)
    return img


def style_ambient(rng, song):
    img = radial((40, 30, 90), (5, 5, 20), 0.5, 0.45)
    d = ImageDraw.Draw(img)
    for _ in range(220):
        x, y, s = rng.randint(0, SIZE), rng.randint(0, SIZE), rng.choice([1, 1, 2, 3])
        c = rng.randint(160, 255)
        d.ellipse((x, y, x + s, y + s), fill=(c, c, 255))
    def planet(d2):
        d2.ellipse((180, 170, 420, 410), fill=(120, 200, 220, 255))
        d2.ellipse((110, 265, 490, 315), outline=(230, 230, 255, 230), width=6)
    glow(img, planet, 30)
    return img


def style_jazz(rng, song, dark=False):
    base = (25, 30, 55) if dark else (120, 70, 40)
    img = gradient(base, (15, 15, 25) if dark else (60, 30, 20))
    d = ImageDraw.Draw(img)
    d.ellipse((90, 70, 510, 490), fill=(20, 20, 20))                 # vinyl
    for r in range(60, 210, 9):
        d.ellipse((300 - r, 280 - r, 300 + r, 280 + r), outline=(45, 45, 45), width=2)
    label = (80, 140, 200) if dark else (230, 170, 60)
    d.ellipse((240, 220, 360, 340), fill=label)
    d.ellipse((293, 273, 307, 287), fill=(20, 20, 20))
    if dark:
        for i in range(5):                                            # smoke
            y = 80 + i * 40
            d.arc((60 + i * 20, y, 360 + i * 30, y + 120), 200, 340, fill=(160, 170, 200), width=3)
    return img


def style_synthwave(rng, song):
    img = gradient((30, 10, 60), (230, 60, 150))
    d = ImageDraw.Draw(img)
    for i, col in enumerate([(255, 220, 90), (255, 160, 90), (255, 100, 120)]):
        d.pieslice((150, 150 + i * 2, 450, 450), 180, 360, fill=col)
    for k in range(5):
        d.rectangle((150, 230 + k * 22, 450, 238 + k * 22), fill=(230, 60, 150))
    d.rectangle((0, 300, SIZE, SIZE), fill=(20, 5, 40))
    for i in range(12):
        y = 300 + (i ** 1.6) * 6
        d.line((0, y, SIZE, y), fill=(0, 255, 230), width=2)
    for x in range(-600, 1201, 60):
        d.line((300, 300, x, SIZE), fill=(0, 255, 230), width=2)
    return img


def style_indie_pop(rng, song):
    img = gradient((120, 200, 230), (250, 190, 200))
    d = ImageDraw.Draw(img)
    x = 0
    while x < SIZE:
        w, h = rng.randint(50, 90), rng.randint(160, 330)
        col = rng.choice([(90, 80, 150), (110, 90, 170), (70, 70, 130)])
        d.rectangle((x, SIZE - h, x + w, SIZE), fill=col)
        for wy in range(SIZE - h + 15, SIZE - 20, 28):
            for wx in range(x + 10, x + w - 10, 18):
                if rng.random() < 0.6:
                    d.rectangle((wx, wy, wx + 8, wy + 12), fill=(255, 230, 140))
        x += w + 4
    for _ in range(25):
        cx, cy = rng.randint(20, 580), rng.randint(20, 260)
        d.line((cx - 4, cy, cx + 4, cy), fill=(255, 255, 255), width=2)
        d.line((cx, cy - 4, cx, cy + 4), fill=(255, 255, 255), width=2)
    return img


def style_hiphop(rng, song):
    img = gradient((15, 15, 15), (45, 40, 30))
    d = ImageDraw.Draw(img)
    for y in range(0, SIZE, 40):                                      # concrete texture
        d.line((0, y, SIZE, y + rng.randint(-8, 8)), fill=(40, 40, 40), width=1)
    def crown(d2):
        pts = [(140, 380), (140, 200), (220, 290), (300, 160), (380, 290), (460, 200), (460, 380)]
        d2.polygon(pts, fill=(240, 190, 60, 255))
        d2.rectangle((140, 380, 460, 420), fill=(220, 165, 40, 255))
        for cx in (140, 300, 460):
            d2.ellipse((cx - 16, 150 if cx == 300 else 190, cx + 16, 182 if cx == 300 else 222),
                       fill=(230, 60, 70, 255))
    glow(img, crown, 20)
    return img


def style_edm(rng, song):
    img = radial((60, 0, 90), (5, 0, 15))
    def rings(d):
        for i, r in enumerate(range(40, 330, 28)):
            col = (0, 255, 230, 255) if i % 2 == 0 else (255, 60, 220, 255)
            d.ellipse((300 - r, 300 - r, 300 + r, 300 + r), outline=col, width=5)
    glow(img, rings, 14)
    d = ImageDraw.Draw(img)
    for i in range(30):                                               # equalizer bars
        h = int(abs(math.sin(i * 0.7)) * 120) + 20
        d.rectangle((i * 20 + 2, 0, i * 20 + 14, h // 2), fill=(255, 255, 255))
    return img


def style_country(rng, song):
    img = gradient((250, 170, 90), (190, 90, 60))
    d = ImageDraw.Draw(img)
    d.ellipse((220, 230, 380, 390), fill=(255, 220, 140))            # setting sun
    d.rectangle((0, 330, SIZE, SIZE), fill=(110, 70, 40))             # field
    for x in range(0, SIZE, 60):                                      # fence
        d.rectangle((x + 20, 360, x + 32, 470), fill=(70, 45, 25))
    d.rectangle((0, 385, SIZE, 395), fill=(70, 45, 25))
    d.rectangle((0, 430, SIZE, 440), fill=(70, 45, 25))
    for _ in range(40):
        x = rng.randint(0, SIZE)
        d.line((x, SIZE, x + rng.randint(-10, 10), SIZE - rng.randint(30, 80)), fill=(200, 160, 80), width=2)
    return img


def style_classical(rng, song):
    img = gradient((15, 25, 70), (60, 90, 160))
    def moon(d):
        d.ellipse((330, 70, 470, 210), fill=(240, 240, 220, 255))
    glow(img, moon, 30)
    d = ImageDraw.Draw(img)
    keys_top = 260
    for i in range(12):                                               # piano keys
        d.rectangle((i * 50, keys_top, i * 50 + 48, keys_top + 200), fill=(245, 245, 240))
    for i in range(12):
        if i % 7 not in (2, 6):
            d.rectangle((i * 50 + 34, keys_top, i * 50 + 64, keys_top + 120), fill=(15, 15, 20))
    return img


def style_metal(rng, song):
    img = gradient((10, 10, 10), (60, 0, 0))
    d = ImageDraw.Draw(img)
    spires = [(100, 160), (190, 90), (300, 40), (410, 90), (500, 160)]
    for x, top in spires:                                             # cathedral silhouette
        d.polygon([(x - 45, 520), (x - 45, top + 80), (x, top), (x + 45, top + 80), (x + 45, 520)],
                  fill=(25, 25, 28))
    d.ellipse((260, 200, 340, 280), outline=(200, 20, 20), width=6)   # rose window
    for a in range(0, 360, 45):
        r = math.radians(a)
        d.line((300, 240, 300 + 38 * math.cos(r), 240 + 38 * math.sin(r)), fill=(200, 20, 20), width=3)
    for _ in range(40):                                               # sparks
        x, y = rng.randint(0, SIZE), rng.randint(420, SIZE)
        d.line((x, y, x + rng.randint(-10, 10), y - rng.randint(10, 40)), fill=(255, 90, 30), width=2)
    return img


def style_rnb(rng, song):
    img = gradient((70, 20, 70), (20, 10, 40))
    def waves(d):
        for k in range(7):
            pts = [(x, 300 + 60 * math.sin(x / 70 + k * 0.6) + (k - 3) * 22) for x in range(0, SIZE + 10, 10)]
            d.line(pts, fill=(230, 120, 200, 200 - k * 18), width=6)
    glow(img, waves, 12)
    return img


def style_reggae(rng, song):
    img = Image.new("RGB", (SIZE, SIZE))
    d = ImageDraw.Draw(img)
    for i, col in enumerate([(40, 140, 70), (250, 210, 50), (210, 50, 40)]):
        d.rectangle((0, i * 200, SIZE, i * 200 + 200), fill=col)
    d.ellipse((190, 140, 410, 360), fill=(255, 240, 180))
    trunk = [(120, 600), (140, 420), (165, 300), (180, 250)]
    d.line(trunk, fill=(60, 40, 20), width=18)
    for a in range(0, 360, 40):                                       # palm leaves
        r = math.radians(a)
        d.line((180, 250, 180 + 120 * math.cos(r), 250 + 60 * math.sin(r)), fill=(20, 80, 40), width=14)
    return img


def style_folk(rng, song):
    img = gradient((200, 215, 170), (110, 140, 100))
    d = ImageDraw.Draw(img)
    d.polygon([(260, 600), (290, 330), (310, 330), (340, 600)], fill=(80, 60, 40))  # trunk
    for _ in range(60):                                               # weeping branches
        x0 = rng.randint(180, 420)
        pts = [(x0 + t * rng.uniform(-0.4, 0.4), 220 + t * 2.2) for t in range(0, 120, 8)]
        d.line([(300, 260)] + pts, fill=(60, 110, 60), width=3)
    d.ellipse((170, 140, 430, 320), fill=(90, 140, 80))
    d.rectangle((0, 540, SIZE, SIZE), fill=(90, 110, 70))             # road
    d.polygon([(250, 600), (350, 600), (310, 540), (290, 540)], fill=(190, 170, 130))
    return img


def style_blues(rng, song):
    img = gradient((15, 25, 60), (40, 60, 110))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 600), (600, 600), (330, 300), (270, 300)], fill=(150, 120, 80))    # road 1
    d.polygon([(0, 380), (0, 470), (600, 360), (600, 300)], fill=(130, 100, 70))      # road 2
    d.line((300, 300, 300, 600), fill=(240, 220, 120), width=4)
    d.rectangle((420, 150, 432, 330), fill=(60, 40, 30))              # signpost
    d.polygon([(432, 170), (540, 170), (560, 190), (540, 210), (432, 210)], fill=(200, 170, 110))
    d.polygon([(420, 240), (320, 240), (300, 260), (320, 280), (420, 280)], fill=(200, 170, 110))
    for _ in range(80):
        x, y = rng.randint(0, SIZE), rng.randint(0, 280)
        d.point((x, y), fill=(220, 220, 255))
    return img


def style_latin(rng, song):
    img = radial((255, 200, 60), (200, 30, 40))
    d = ImageDraw.Draw(img)
    for a in range(0, 360, 15):                                       # sunburst
        r = math.radians(a)
        d.polygon([(300, 300), (300 + 450 * math.cos(r), 300 + 450 * math.sin(r)),
                   (300 + 450 * math.cos(r + 0.12), 300 + 450 * math.sin(r + 0.12))],
                  fill=(255, 120, 40) if a % 30 == 0 else (230, 60, 50))
    def flame(d2):
        d2.polygon([(300, 120), (380, 320), (340, 300), (360, 420), (300, 360), (240, 420),
                    (260, 300), (220, 320)], fill=(255, 230, 80, 255))
    glow(img, flame, 20)
    return img


def style_library(rng, song):
    img = gradient((70, 55, 50), (35, 28, 30))
    d = ImageDraw.Draw(img)
    for shelf_y in (60, 200, 340):
        d.rectangle((0, shelf_y + 120, SIZE, shelf_y + 132), fill=(90, 60, 40))
        x = 10
        while x < SIZE - 20:
            w = rng.randint(18, 34); h = rng.randint(80, 118)
            col = rng.choice([(170, 80, 70), (80, 110, 150), (190, 160, 90), (90, 130, 100), (140, 100, 160)])
            d.rectangle((x, shelf_y + 120 - h, x + w, shelf_y + 120), fill=col)
            x += w + rng.randint(2, 6)
    lamp = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lamp).ellipse((330, 40, 590, 300), fill=(255, 210, 120, 90))
    lamp = lamp.filter(ImageFilter.GaussianBlur(40))
    img.paste(lamp, (0, 0), lamp)
    return img


def style_focus(rng, song):
    img = gradient((20, 60, 70), (10, 25, 35))
    d = ImageDraw.Draw(img)
    def headphones(d2):
        d2.arc((170, 110, 430, 370), 180, 360, fill=(120, 230, 210, 255), width=22)
        d2.rounded_rectangle((150, 230, 220, 350), 22, fill=(120, 230, 210, 255))
        d2.rounded_rectangle((380, 230, 450, 350), 22, fill=(120, 230, 210, 255))
    glow(img, headphones, 18)
    for i in range(24):                                               # calm sine "flow"
        pts = [(x, 420 + 18 * math.sin(x / 45 + i * 0.25) + i * 2) for x in range(0, SIZE + 10, 10)]
        d.line(pts, fill=(60, 140, 140), width=1)
    return img


def style_gym(rng, song):
    img = gradient((200, 20, 40), (40, 0, 30))
    d = ImageDraw.Draw(img)
    for _ in range(26):                                               # speed lines
        y = rng.randint(40, 520); x = rng.randint(-100, 300)
        d.line((x, y, x + rng.randint(150, 350), y - 60), fill=(255, 120, 120), width=3)
    def dumbbell(d2):
        d2.rounded_rectangle((180, 270, 420, 300), 10, fill=(240, 240, 240, 255))
        for x in (150, 380):
            d2.rounded_rectangle((x, 190, x + 70, 380), 14, fill=(30, 30, 30, 255))
            d2.rounded_rectangle((x + 10, 200, x + 60, 370), 10, outline=(255, 220, 60, 255), width=5)
    glow(img, dumbbell, 16)
    return img


STYLES = {
    "pop": style_pop, "lofi": style_lofi, "rock": style_rock, "ambient": style_ambient,
    "jazz": style_jazz, "synthwave": style_synthwave, "indie pop": style_indie_pop,
    "hip-hop": style_hiphop, "edm": style_edm, "country": style_country,
    "classical": style_classical, "metal": style_metal, "r&b": style_rnb,
    "reggae": style_reggae, "folk": style_folk, "blues": style_blues, "latin": style_latin,
}


def artwork(song, rng):
    genre, mood = song["genre"], song["mood"]
    if genre == "pop" and mood == "romantic":
        return style_pop_romantic(rng, song)
    if genre == "jazz" and mood == "moody":
        return style_jazz(rng, song, dark=True)
    if genre == "lofi" and mood == "focused":
        return style_focus(rng, song)
    if genre == "lofi" and song["title"] == "Library Rain":
        return style_library(rng, song)
    if genre == "pop" and mood == "intense":
        return style_gym(rng, song)
    return STYLES.get(genre, style_ambient)(rng, song)


def vary(img, song, index_in_genre):
    """Give later songs of the same genre their own palette and layout (ids 23+ only)."""
    if int(song["id"]) <= 22 or index_in_genre == 0:
        return img
    shifts = [0, 40, -35, 80, -70]
    shift = shifts[index_in_genre % len(shifts)]
    h, sat, v = img.convert("HSV").split()
    h = h.point(lambda x: (x + shift) % 256)
    out = Image.merge("HSV", (h, sat, v)).convert("RGB")
    if index_in_genre % 2 == 1:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    return out


# ---------------------------------------------------------------- text

def add_text(img, artist, album):
    img = img.convert("RGBA")
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(190):                                              # dark band at bottom
        sd.line((0, SIZE - i, SIZE, SIZE - i), fill=(0, 0, 0, int(235 * (1 - i / 190) ** 0.7)))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)

    size = 46
    f_album = font("bold", size)
    while d.textlength(album.upper(), font=f_album) > SIZE - 60 and size > 20:
        size -= 2
        f_album = font("bold", size)
    f_artist = font("regular", 26)
    d.text((30, SIZE - 100), album.upper(), font=f_album, fill=(255, 255, 255))
    d.text((32, SIZE - 48), artist, font=f_artist, fill=(220, 220, 220))
    d.rectangle((30, SIZE - 112, 90, SIZE - 108), fill=(255, 255, 255))   # accent bar
    return img.convert("RGB")


def make_cover(song: dict, index_in_genre: int = 0) -> Image.Image:
    rng = random.Random(int(song["id"]) * 7919)                       # same cover every run
    art = vary(artwork(song, rng), song, index_in_genre)
    grain(art, rng, 8)
    return add_text(art, song["artist"], ALBUMS.get(int(song["id"]), song["title"]))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SONGS_CSV, newline="", encoding="utf-8") as f:
        songs = list(csv.DictReader(f))
    seen = {}
    for song in songs:
        idx = seen.get(song["genre"], 0)
        seen[song["genre"]] = idx + 1
        path = OUT_DIR / f"{int(song['id']):02d}.png"
        make_cover(song, idx).save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}  {song['title']} -> {ALBUMS.get(int(song['id']))}")
    print(f"Done: {len(songs)} covers in {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
