# -*- coding: utf-8 -*-
"""
Mapa podróży – aplikacja na Androida (Python + Kivy).

Pokazuje polityczną mapę świata z granicami państw. Dotknij państwa
i naciśnij „Byłem tu” – państwo podświetli się na zielono.
Odwiedzone państwa zapisują się w pamięci telefonu.
"""
import json
import math
import os
import unicodedata

from kivy.config import Config
from kivy.utils import platform

# Na komputerze: okno o proporcjach telefonu i brak „czerwonych kropek”
# symulujących multitouch pod prawym przyciskiem myszy.
Config.set("input", "mouse", "mouse,multitouch_on_demand")
if platform not in ("android", "ios"):
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "840")

from kivy.animation import Animation  # noqa: E402
from kivy.app import App  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.graphics import (Color, Ellipse, Mesh, PopMatrix,  # noqa: E402
                           PushMatrix, Rectangle, Scale, StencilPop,
                           StencilPush, StencilUnUse, StencilUse, Translate)
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.properties import (BooleanProperty, ColorProperty,  # noqa: E402
                             NumericProperty, StringProperty)
from kivy.uix.behaviors import ButtonBehavior  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.screenmanager import Screen, SlideTransition  # noqa: E402
from kivy.uix.stencilview import StencilView  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402
from kivy.utils import get_color_from_hex as hexc  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WORLD_FILE = os.path.join(APP_DIR, "data", "world.json")

# ---------------------------------------------------------------- kolory ---
OCEAN = hexc("#A9D3EE")
BACKGROUND = hexc("#E3E9EE")       # tło poza ramką mapy
FRAME = hexc("#7D8C99")
BORDER = hexc("#4F4A45")
VISITED = hexc("#2FA84F")          # odwiedzone – zielony
# delikatnie różne odcienie zieleni, żeby sąsiednie odwiedzone państwa
# nie zlewały się w jedną plamę
VISITED_SHADES = {
    1: hexc("#2FA84F"), 2: hexc("#38B258"), 3: hexc("#29A049"),
    4: hexc("#3DB65E"), 5: hexc("#2BA54C"), 6: hexc("#34AD54"),
    7: hexc("#259A45"),
}
SELECTED = hexc("#5B9BE0")         # zaznaczone (jeszcze nie odwiedzone)
SELECTED_VISITED = hexc("#1B7A35")  # zaznaczone i odwiedzone
MARKER_IDLE = hexc("#FFFFFF")
# Pastelowa paleta mapy politycznej (bez zieleni, żeby nie myliła się
# z odwiedzonymi). Sąsiednie państwa dostają różne kolory (MAPCOLOR7).
PALETTE = {
    1: hexc("#F4D9A6"),
    2: hexc("#F2BFA7"),
    3: hexc("#D7C4E8"),
    4: hexc("#F7EBA8"),
    5: hexc("#EBC3D7"),
    6: hexc("#E3D5C1"),
    7: hexc("#C9D3E8"),
}
ANTARCTICA = hexc("#F4F6F8")

CONTINENTS_PL = {
    "Africa": "Afryka",
    "Asia": "Azja",
    "Europe": "Europa",
    "North America": "Ameryka Północna",
    "South America": "Ameryka Południowa",
    "Oceania": "Oceania",
    "Antarctica": "Antarktyda",
    "Seven seas (open ocean)": "Wyspy oceaniczne",
}

TINY_AREA_KM2 = 3000   # mniejsze obszary dostają kropkę, żeby dało się je trafić
MAX_ZOOM = 45          # maksymalne przybliżenie względem widoku całego świata
DOTS_ZOOM = 2.5        # od tego przybliżenia widać kropki nieodwiedzonych maluchów
MAP_BOTTOM_LAT = -78   # niżej jest tylko lód Antarktydy – nie marnujmy ekranu


# ------------------------------------------------------------ pomocnicze ---
def miller(lon, lat):
    """Odwzorowanie walcowe Millera – ładniejsze niż zwykłe lon/lat."""
    lat = max(-89.5, min(89.5, lat))
    y = 1.25 * math.log(math.tan(math.pi / 4 + 0.4 * math.radians(lat)))
    return lon, math.degrees(y)


def point_in_rings(x, y, rings):
    """Test punkt-w-wielokącie (reguła parzystości, obsługuje dziury)."""
    inside = False
    for r in rings:
        n = len(r) // 2
        xj, yj = r[-2], r[-1]
        for i in range(n):
            xi, yi = r[2 * i], r[2 * i + 1]
            if (yi > y) != (yj > y) and \
                    x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            xj, yj = xi, yi
    return inside


def ring_area(r):
    a = 0.0
    n = len(r) // 2
    for i in range(n):
        j = (i + 1) % n
        a += r[2 * i] * r[2 * j + 1] - r[2 * j] * r[2 * i + 1]
    return abs(a) / 2


def bbox_of(rings):
    xs = rings[0][0::2]
    ys = rings[0][1::2]
    return min(xs), min(ys), max(xs), max(ys)


_PL = "aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż"


def pl_sort_key(text):
    """Sortowanie wg polskiego alfabetu (ą po a, ł po l, ż na końcu…)."""
    key = []
    for ch in text.lower():
        if ch in _PL:
            key.append(_PL.index(ch) * 2)
        else:
            base = unicodedata.normalize("NFD", ch)[0]
            key.append(_PL.index(base) * 2 + 1 if base in _PL else -1)
    return key


def fold(text):
    """Do wyszukiwania: „slowacja” znajdzie „Słowacja”."""
    text = text.lower().replace("ł", "l")
    return "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if unicodedata.category(ch) != "Mn")


def countries_word(n):
    if n == 1:
        return "państwo"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "państwa"
    return "państw"


# ----------------------------------------------------------------- dane ---
class Country:
    def __init__(self, d):
        self.id = d["id"]
        self.name = d["name"]
        self.continent = CONTINENTS_PL.get(d["continent"], d["continent"])
        self.sovereign = d["sovereign"]
        self.color_idx = d["color"]
        self.area = d["area"]
        self.label = tuple(d["label"])   # współrzędne już w odwzorowaniu
        self.fold = fold(self.name)
        self.sort_key = pl_sort_key(self.name)
        self.subtitle = self.continent + (
            "" if self.sovereign else " · terytorium")

        # współrzędne są już przeliczone na odwzorowanie Millera,
        # a trójkąty policzone z góry (tools/prepare_data.py)
        self.polys = [p["rings"] for p in d["polys"]]
        self._tris = [p["tri"] for p in d["polys"]]
        self.bboxes = [bbox_of(p) for p in self.polys]
        # największy wielokąt (np. Francja europejska, bez Gujany)
        areas = [ring_area(p[0]) for p in self.polys]
        main = max(range(len(areas)), key=areas.__getitem__)
        self.main_bbox = self.bboxes[main]
        self.main_size = max(self.main_bbox[2] - self.main_bbox[0],
                             self.main_bbox[3] - self.main_bbox[1])
        self.tiny = self.area < TINY_AREA_KM2

        # elementy grafiki (ustawiane przez MapView)
        self.fill = None
        self.m_fill = None
        self.m_ring = None
        self.m_dot = None
        self.m_line = None

    def triangles(self):
        """Siatki trójkątów do narysowania (wierzchołki x, y, u, v)."""
        chunks = []
        verts, idx = [], []
        for rings, tri in zip(self.polys, self._tris):
            n = sum(len(r) for r in rings) // 2
            base = len(verts) // 4
            if base + n > 65000:          # limit indeksów w jednej siatce
                chunks.append((verts, idx))
                verts, idx, base = [], [], 0
            for r in rings:
                for i in range(0, len(r), 2):
                    verts.extend((r[i], r[i + 1], 0, 0))
            idx.extend(base + i for i in tri)
        if idx:
            chunks.append((verts, idx))
        return chunks


def load_countries():
    with open(WORLD_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [Country(d) for d in data["countries"]]


# --------------------------------------------------------------- mapa ---
class MapView(StencilView):
    """Mapa z przesuwaniem (1 palec), zoomem (2 palce / kółko / przyciski)
    i wybieraniem państwa dotknięciem."""

    zoom = NumericProperty(1.0)
    ox = NumericProperty(0.0)
    oy = NumericProperty(0.0)
    __events__ = ("on_select",)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.countries = []
        self.tiny = []
        self.visited = set()
        self.selected = None
        self._touches = []
        self._pinched = False
        self._ready = False
        self._base = None
        self._center_map = None
        self.bind(pos=self._on_geom, size=self._on_geom,
                  zoom=self._apply, ox=self._apply, oy=self._apply)

    def on_select(self, country):
        pass

    # ---- budowa grafiki
    def set_countries(self, countries, visited):
        self.countries = countries
        self.visited = visited
        self.tiny = [c for c in countries if c.tiny]
        xs = [b for c in countries for bb in c.bboxes for b in (bb[0], bb[2])]
        ys = [b for c in countries for bb in c.bboxes for b in (bb[1], bb[3])]
        bottom = max(min(ys), miller(0, MAP_BOTTOM_LAT)[1])
        x0, y0, x1, y1 = min(xs), bottom, max(xs), max(ys) + 2
        self.map_bounds = (x0, y0, x1, y1)
        frame = dict(pos=(x0, y0), size=(x1 - x0, y1 - y0))

        with self.canvas:
            Color(*BACKGROUND)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            PushMatrix()
            self._tr = Translate(0, 0)
            self._sc = Scale(1, 1, 1)
            # wszystko rysujemy tylko wewnątrz ramki mapy
            StencilPush()
            Rectangle(**frame)
            StencilUse()
            Color(*OCEAN)
            Rectangle(**frame)
            for c in countries:
                c.fill = Color(*self.fill_color(c))
                for verts, idx in c.triangles():
                    Mesh(vertices=verts, indices=idx, mode="triangles")
            Color(*BORDER)
            for verts, idx in self._border_meshes():
                Mesh(vertices=verts, indices=idx, mode="lines")
            for c in self.tiny:
                c.m_ring = Color(*BORDER)
                c.m_line = Ellipse()
                c.m_fill = Color(*self.marker_color(c))
                c.m_dot = Ellipse()
            StencilUnUse()
            Rectangle(**frame)
            StencilPop()
            Color(*FRAME)
            Mesh(vertices=[x0, y0, 0, 0, x1, y0, 0, 0, x1, y1, 0, 0,
                           x0, y1, 0, 0], indices=[0, 1, 2, 3],
                 mode="line_loop")
            PopMatrix()
        self._ready = True
        self._on_geom()

    def _border_meshes(self):
        """Wszystkie granice jako kilka dużych siatek linii – szybkie."""
        out, verts, idx = [], [], []
        for c in self.countries:
            for rings in c.polys:
                for r in rings:
                    n = len(r) // 2
                    base = len(verts) // 4
                    if base + n > 65000:
                        out.append((verts, idx))
                        verts, idx, base = [], [], 0
                    for i in range(n):
                        verts.extend((r[2 * i], r[2 * i + 1], 0, 0))
                    for i in range(n):
                        j = (i + 1) % n
                        if not self._artificial(r, i, j):
                            idx.extend((base + i, base + j))
        if idx:
            out.append((verts, idx))
        return out

    @staticmethod
    def _artificial(r, i, j):
        """Odcinki „cięcia” danych: wzdłuż południka 180° i bieguna."""
        x1, y1, x2, y2 = r[2 * i], r[2 * i + 1], r[2 * j], r[2 * j + 1]
        if abs(x1) > 179.9 and abs(x2) > 179.9 and x1 * x2 > 0:
            return True
        return y1 < -125 and y2 < -125   # okolice bieguna płd. (Miller)

    # ---- kolory
    def fill_color(self, c):
        v = c.id in self.visited
        if c is self.selected:
            return SELECTED_VISITED if v else SELECTED
        if v:
            return VISITED_SHADES.get(c.color_idx, VISITED)
        if c.id == "ATA":
            return ANTARCTICA
        return PALETTE.get(c.color_idx, PALETTE[1])

    def marker_color(self, c):
        if c is self.selected:
            return SELECTED_VISITED if c.id in self.visited else SELECTED
        return VISITED if c.id in self.visited else MARKER_IDLE

    def refresh_country(self, c):
        if c is None or c.fill is None:
            return
        c.fill.rgba = self.fill_color(c)
        if c.tiny:
            c.m_fill.rgba = self.marker_color(c)

    def select(self, c):
        prev, self.selected = self.selected, c
        self.refresh_country(prev)
        self.refresh_country(c)
        self._apply()

    # ---- geometria widoku
    @property
    def base_scale(self):
        x0, y0, x1, y1 = self.map_bounds
        return min(self.width / (x1 - x0), self.height / (y1 - y0))

    def to_map(self, x, y):
        return (x - self.ox) / self.zoom, (y - self.oy) / self.zoom

    def to_screen(self, mx, my):
        return mx * self.zoom + self.ox, my * self.zoom + self.oy

    def _clamped(self, s, ox, oy):
        """Pilnuje, żeby mapa nie „uciekła” poza ekran."""
        x0, y0, x1, y1 = self.map_bounds
        w, h = (x1 - x0) * s, (y1 - y0) * s
        left, bottom = ox + x0 * s, oy + y0 * s
        if w <= self.width:
            left = self.x + (self.width - w) / 2
        else:
            left = min(self.x, max(self.right - w, left))
        if h <= self.height:
            bottom = self.y + (self.height - h) / 2
        else:
            bottom = min(self.y, max(self.top - h, bottom))
        return left - x0 * s, bottom - y0 * s

    def _clamp(self):
        self.ox, self.oy = self._clamped(self.zoom, self.ox, self.oy)

    def _on_geom(self, *a):
        if hasattr(self, "_bg"):
            self._bg.pos = self.pos
            self._bg.size = self.size
        if not self._ready or self.width < 2 or self.height < 2:
            return
        base = self.base_scale
        if self._base is None or self._center_map is None:
            self.zoom = base
            x0, y0, x1, y1 = self.map_bounds
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        else:   # obrót ekranu itp. – zachowaj środek i przybliżenie
            self.zoom = max(base, self.zoom / self._base * base)
            cx, cy = self._center_map
        self._base = base
        self.ox = self.center_x - cx * self.zoom
        self.oy = self.center_y - cy * self.zoom
        self._clamp()
        self._apply()

    def _apply(self, *a):
        if not self._ready:
            return
        s = self.zoom
        self._tr.xy = (self.ox, self.oy)
        self._sc.xyz = (s, s, 1)
        self._center_map = self.to_map(*self.center)
        # kropki małych państw – stały rozmiar na ekranie
        r_in, r_out = dp(3.8) / s, dp(5.2) / s
        show_idle = s >= self.min_zoom * DOTS_ZOOM
        for c in self.tiny:
            lx, ly = c.label
            important = c is self.selected or c.id in self.visited
            too_big = c.main_size * s > dp(26)
            if (too_big or not (show_idle or important)) and \
                    c is not self.selected:
                c.m_dot.size = c.m_line.size = (0, 0)
                continue
            k = 1.35 if c is self.selected else 1.0
            c.m_line.pos = (lx - r_out * k, ly - r_out * k)
            c.m_line.size = (2 * r_out * k, 2 * r_out * k)
            c.m_dot.pos = (lx - r_in * k, ly - r_in * k)
            c.m_dot.size = (2 * r_in * k, 2 * r_in * k)

    # ---- zoom
    @property
    def min_zoom(self):
        return self.base_scale

    @property
    def max_zoom(self):
        return self.base_scale * MAX_ZOOM

    def _zoom_at(self, px, py, factor):
        s0 = self.zoom
        s1 = max(self.min_zoom, min(self.max_zoom, s0 * factor))
        f = s1 / s0
        self.ox = px - (px - self.ox) * f
        self.oy = py - (py - self.oy) * f
        self.zoom = s1

    def animate_to(self, s, cx, cy, d=0.45):
        s = max(self.min_zoom, min(self.max_zoom, s))
        ox, oy = self._clamped(s, self.center_x - cx * s,
                               self.center_y - cy * s)
        Animation.cancel_all(self)
        Animation(zoom=s, ox=ox, oy=oy, d=d, t="out_cubic").start(self)

    def zoom_by(self, factor, pos=None):
        px, py = pos or self.center
        mx, my = self.to_map(px, py)
        s = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        # punkt pod palcem zostaje w miejscu
        cx = mx - (px - self.center_x) / s
        cy = my - (py - self.center_y) / s
        self.animate_to(s, cx, cy, d=0.3)

    def reset_view(self):
        x0, y0, x1, y1 = self.map_bounds
        self.animate_to(self.min_zoom, (x0 + x1) / 2, (y0 + y1) / 2)

    def zoom_to(self, c):
        x0, y0, x1, y1 = c.main_bbox
        w, h = max(x1 - x0, 0.3), max(y1 - y0, 0.3)
        s = min(self.width * 0.55 / w, self.height * 0.5 / h)
        self.animate_to(s, (x0 + x1) / 2, (y0 + y1) / 2, d=0.6)

    # ---- wybieranie państwa
    def country_at(self, x, y):
        # najbliższa widoczna kropka małego państwa
        dot, dot_d = None, dp(16)
        for c in self.tiny:
            if c.m_dot.size[0] == 0:
                continue
            sx, sy = self.to_screen(*c.label)
            d = math.hypot(sx - x, sy - y)
            if d < dot_d:
                dot, dot_d = c, d
        # państwo pod palcem
        hit = None
        mx, my = self.to_map(x, y)
        for c in self.countries:
            for bb, rings in zip(c.bboxes, c.polys):
                if bb[0] <= mx <= bb[2] and bb[1] <= my <= bb[3] and \
                        point_in_rings(mx, my, rings):
                    hit = c
                    break
            if hit:
                break
        # kropka wygrywa, gdy trafiono prawie w nią albo obok nie ma lądu
        if dot and (hit is None or hit is dot or dot_d < dp(6)):
            return dot
        return hit

    # ---- dotyk
    def on_touch_down(self, touch):
        if not self._ready or not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            if touch.button == "scrolldown":
                self._zoom_at(*touch.pos, 1.2)
            elif touch.button == "scrollup":
                self._zoom_at(*touch.pos, 1 / 1.2)
            self._clamp()
            return True
        Animation.cancel_all(self)
        touch.grab(self)
        self._touches.append(touch)
        touch.ud["mv_start"] = touch.pos
        touch.ud["mv_pos"] = touch.pos
        touch.ud["mv_moved"] = False
        if len(self._touches) > 1:
            self._pinched = True
        elif touch.is_double_tap:
            touch.ud["mv_double"] = True
            self.zoom_by(2.2, touch.pos)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        sx, sy = touch.ud["mv_start"]
        if abs(touch.x - sx) > dp(8) or abs(touch.y - sy) > dp(8):
            touch.ud["mv_moved"] = True
        prev = touch.ud["mv_pos"]
        touch.ud["mv_pos"] = touch.pos
        if len(self._touches) == 1:
            self.ox += touch.x - prev[0]
            self.oy += touch.y - prev[1]
        elif touch in self._touches[:2]:
            a, b = self._touches[:2]
            other = b if touch is a else a
            ox_, oy_ = other.ud["mv_pos"]
            d_old = math.hypot(prev[0] - ox_, prev[1] - oy_)
            d_new = math.hypot(touch.x - ox_, touch.y - oy_)
            if d_old > 1:
                m0 = ((prev[0] + ox_) / 2, (prev[1] + oy_) / 2)
                m1 = ((touch.x + ox_) / 2, (touch.y + oy_) / 2)
                self.ox += m1[0] - m0[0]
                self.oy += m1[1] - m0[1]
                self._zoom_at(m1[0], m1[1], d_new / d_old)
        self._clamp()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if touch in self._touches:
            self._touches.remove(touch)
        is_tap = not (touch.ud.get("mv_moved") or self._pinched
                      or touch.ud.get("mv_double"))
        if not self._touches:
            self._pinched = False
        if is_tap:
            c = self.country_at(*touch.pos)
            self.select(c)
            self.dispatch("on_select", c)
        return True


# ------------------------------------------------------------ ekrany ---
class MapScreen(Screen):
    pass


class ListScreen(Screen):
    pass


class FlatButton(Button):
    bg = ColorProperty("#2FA84F")
    fg = ColorProperty("#FFFFFF")
    radius = NumericProperty(dp(12))


class CheckMark(Widget):
    active = BooleanProperty(False)


class CountryRow(ButtonBehavior, BoxLayout):
    code = StringProperty("")
    name = StringProperty("")
    subtitle = StringProperty("")
    visited = BooleanProperty(False)


KV = r"""
#:import hexc kivy.utils.get_color_from_hex

<Label>:
    color: hexc('#1F2A33')

<FlatButton>:
    background_normal: ''
    background_down: ''
    background_disabled_normal: ''
    background_color: 0, 0, 0, 0
    color: self.fg
    disabled_color: self.fg
    bold: True
    font_size: sp(15)
    canvas.before:
        Color:
            rgba: (self.bg[0] * .85, self.bg[1] * .85, self.bg[2] * .85, self.bg[3]) if self.state == 'down' else self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radius]

<SegButton@ToggleButton>:
    group: 'filter'
    allow_no_selection: False
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: (1, 1, 1, 1) if self.state == 'down' else hexc('#2D5873')
    font_size: sp(14)
    bold: self.state == 'down'
    canvas.before:
        Color:
            rgba: hexc('#2D5873') if self.state == 'down' else hexc('#E3EAF0')
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(17)]

<MapButton@Button>:
    size_hint: None, None
    size: dp(48), dp(48)
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: hexc('#2B3A45')
    font_size: sp(26)
    canvas.before:
        Color:
            rgba: 0, 0, 0, .18
        Ellipse:
            pos: self.x + dp(1), self.y - dp(2)
            size: self.size
        Color:
            rgba: (.9, .92, .94, 1) if self.state == 'down' else (1, 1, 1, 1)
        Ellipse:
            pos: self.pos
            size: self.size

<GlobeButton@MapButton>:
    canvas.after:
        Color:
            rgba: hexc('#2B3A45')
        Line:
            circle: self.center_x, self.center_y, dp(11)
            width: dp(1.3)
        Line:
            ellipse: self.center_x - dp(5), self.center_y - dp(11), dp(10), dp(22)
            width: dp(1.3)
        Line:
            points: self.center_x - dp(11), self.center_y, self.center_x + dp(11), self.center_y
            width: dp(1.3)

<CheckMark>:
    size_hint: None, None
    size: dp(26), dp(26)
    canvas:
        Color:
            rgba: hexc('#2FA84F') if self.active else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(7)]
        Color:
            rgba: (0, 0, 0, 0) if self.active else hexc('#B5BDC4')
        Line:
            rounded_rectangle: self.x + dp(1), self.y + dp(1), self.width - dp(2), self.height - dp(2), dp(6)
            width: dp(1.4)
        Color:
            rgba: (1, 1, 1, 1) if self.active else (0, 0, 0, 0)
        Line:
            points: self.x + dp(6.5), self.y + dp(13), self.x + dp(11), self.y + dp(8.5), self.x + dp(19.5), self.y + dp(17.5)
            width: dp(2)
            cap: 'round'
            joint: 'round'

<TopBar@BoxLayout>:
    size_hint_y: None
    height: dp(64)
    padding: dp(16), dp(8), dp(12), dp(8)
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: hexc('#1F3A4D')
        Rectangle:
            pos: self.pos
            size: self.size

<CountryRow>:
    size_hint_y: None
    height: dp(62)
    padding: dp(16), 0, dp(12), 0
    spacing: dp(14)
    on_release: app.toggle_visited(root.code)
    canvas.before:
        Color:
            rgba: (.92, .95, .97, 1) if self.state == 'down' else (1, 1, 1, 1)
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: 0, 0, 0, .07
        Rectangle:
            pos: self.x + dp(56), self.y
            size: self.width - dp(56), dp(1)
    AnchorLayout:
        size_hint_x: None
        width: dp(26)
        CheckMark:
            active: root.visited
    BoxLayout:
        orientation: 'vertical'
        padding: 0, dp(10)
        Label:
            text: root.name
            font_size: sp(16)
            bold: root.visited
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
            shorten_from: 'right'
        Label:
            text: root.subtitle
            font_size: sp(12.5)
            color: hexc('#6B7780')
            text_size: self.size
            halign: 'left'
            valign: 'middle'
    FlatButton:
        text: 'Mapa'
        size_hint: None, None
        size: dp(64), dp(34)
        pos_hint: {'center_y': .5}
        bg: hexc('#E8EEF3')
        fg: hexc('#2D5873')
        font_size: sp(13)
        on_release: app.show_on_map(root.code)

<MapScreen>:
    name: 'map'
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            BoxLayout:
                orientation: 'vertical'
                Label:
                    text: 'Mapa podróży'
                    color: 1, 1, 1, 1
                    bold: True
                    font_size: sp(19)
                    text_size: self.size
                    halign: 'left'
                    valign: 'middle'
                Label:
                    text: app.stats_text
                    color: 1, 1, 1, .8
                    font_size: sp(13)
                    text_size: self.size
                    halign: 'left'
                    valign: 'middle'
                    shorten: True
            FlatButton:
                text: 'Lista'
                size_hint: None, None
                size: dp(80), dp(42)
                pos_hint: {'center_y': .5}
                bg: hexc('#3E6A87')
                on_release: app.open_list()
        FloatLayout:
            MapView:
                id: mapview
                size_hint: 1, 1
                pos_hint: {'x': 0, 'y': 0}
                on_select: app.on_map_select(args[1])
            BoxLayout:
                orientation: 'vertical'
                size_hint: None, None
                size: dp(48), dp(48) * 3 + dp(12) * 2
                spacing: dp(12)
                pos: self.parent.right - self.width - dp(14), self.parent.y + dp(14)
                MapButton:
                    text: '+'
                    on_release: mapview.zoom_by(2)
                MapButton:
                    text: '−'
                    on_release: mapview.zoom_by(0.5)
                GlobeButton:
                    on_release: mapview.reset_view()
        BoxLayout:
            size_hint_y: None
            height: dp(86)
            padding: dp(16), dp(12)
            spacing: dp(12)
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
                Color:
                    rgba: 0, 0, 0, .12
                Rectangle:
                    pos: self.x, self.top - dp(1)
                    size: self.width, dp(1)
            BoxLayout:
                orientation: 'vertical'
                Label:
                    text: app.sel_name if app.sel_code else 'Dotknij państwa na mapie'
                    bold: bool(app.sel_code)
                    font_size: sp(19) if app.sel_code else sp(16)
                    text_size: self.size
                    halign: 'left'
                    valign: 'middle'
                    shorten: True
                    shorten_from: 'right'
                Label:
                    text: app.sel_sub if app.sel_code else 'i oznacz je jako odwiedzone'
                    color: hexc('#6B7780')
                    font_size: sp(13.5)
                    text_size: self.size
                    halign: 'left'
                    valign: 'middle'
                    shorten: True
            FlatButton:
                size_hint: None, None
                size: dp(128), dp(50)
                pos_hint: {'center_y': .5}
                opacity: 1 if app.sel_code else 0
                disabled: not app.sel_code
                text: 'Usuń' if app.sel_visited else 'Byłem tu'
                bg: hexc('#EEF0F2') if app.sel_visited else hexc('#2FA84F')
                fg: hexc('#B3261E') if app.sel_visited else (1, 1, 1, 1)
                font_size: sp(16)
                on_release: app.toggle_selected()

<ListScreen>:
    name: 'list'
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: hexc('#F4F6F8')
            Rectangle:
                pos: self.pos
                size: self.size
        TopBar:
            FlatButton:
                text: '‹ Mapa'
                size_hint: None, None
                size: dp(88), dp(42)
                pos_hint: {'center_y': .5}
                bg: hexc('#3E6A87')
                on_release: app.open_map()
            Label:
                text: 'Państwa'
                color: 1, 1, 1, 1
                bold: True
                font_size: sp(19)
                text_size: self.size
                halign: 'left'
                valign: 'middle'
            Label:
                text: app.list_count_text
                color: 1, 1, 1, .8
                font_size: sp(13)
                size_hint_x: None
                width: dp(110)
                text_size: self.size
                halign: 'right'
                valign: 'middle'
        BoxLayout:
            size_hint_y: None
            height: dp(62)
            padding: dp(12), dp(10), dp(12), dp(6)
            TextInput:
                id: search
                hint_text: 'Szukaj państwa…'
                multiline: False
                write_tab: False
                font_size: sp(16)
                padding: dp(14), dp(12)
                background_normal: ''
                background_active: ''
                background_color: 1, 1, 1, 1
                cursor_color: hexc('#2D5873')
                on_text: app.refresh_list()
        BoxLayout:
            size_hint_y: None
            height: dp(50)
            padding: dp(12), dp(6), dp(12), dp(10)
            spacing: dp(8)
            SegButton:
                text: 'Wszystkie'
                state: 'down'
                on_release: app.set_filter('all')
            SegButton:
                text: 'Odwiedzone'
                on_release: app.set_filter('visited')
            SegButton:
                text: 'Do odwiedzenia'
                on_release: app.set_filter('todo')
        RecycleView:
            id: rv
            viewclass: 'CountryRow'
            bar_width: dp(4)
            RecycleBoxLayout:
                default_size: None, dp(62)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'

ScreenManager:
    MapScreen:
    ListScreen:
"""


# ------------------------------------------------------------ aplikacja ---
class TravelMapApp(App):
    title = "Mapa podróży"
    stats_text = StringProperty("")
    list_count_text = StringProperty("")
    sel_code = StringProperty("")
    sel_name = StringProperty("")
    sel_sub = StringProperty("")
    sel_visited = BooleanProperty(False)

    def build(self):
        Window.clearcolor = BACKGROUND
        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self._on_key)

        self.countries = load_countries()
        self.by_code = {c.id: c for c in self.countries}
        self.sorted_countries = sorted(self.countries, key=lambda c: c.sort_key)
        self.total_area = sum(c.area for c in self.countries)
        self.visited = self.load_visited()
        self.filter_mode = "all"

        self.sm = Builder.load_string(KV)
        self.sm.transition = SlideTransition(duration=0.25)
        self.mapview = self.sm.get_screen("map").ids.mapview
        self.list_ids = self.sm.get_screen("list").ids
        self.mapview.set_countries(self.countries, self.visited)
        self.update_stats()
        return self.sm

    # ---- zapis / odczyt
    @property
    def save_path(self):
        return os.path.join(self.user_data_dir, "visited.json")

    def load_visited(self):
        try:
            with open(self.save_path, encoding="utf-8") as f:
                codes = json.load(f).get("visited", [])
            return {c for c in codes if c in self.by_code}
        except (OSError, ValueError):
            return set()

    def save_visited(self):
        tmp = self.save_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"visited": sorted(self.visited)}, f)
        os.replace(tmp, self.save_path)

    # ---- logika
    def update_stats(self):
        n = len(self.visited)
        area = sum(self.by_code[c].area for c in self.visited)
        pct = f"{100 * area / self.total_area:.1f}".replace(".", ",")
        self.stats_text = (f"Odwiedzono {n} {countries_word(n)}"
                           f" · {pct}% lądów świata")
        self.list_count_text = f"{n} / {len(self.countries)}"

    def _update_selection_info(self):
        c = self.mapview.selected
        if c is None:
            self.sel_code = self.sel_name = self.sel_sub = ""
            self.sel_visited = False
            return
        self.sel_visited = c.id in self.visited
        self.sel_name = c.name
        self.sel_sub = c.subtitle + (" · odwiedzone" if self.sel_visited
                                     else " · jeszcze nie")
        self.sel_code = c.id

    def on_map_select(self, country):
        self._update_selection_info()

    def toggle_visited(self, code):
        c = self.by_code[code]
        if code in self.visited:
            self.visited.discard(code)
        else:
            self.visited.add(code)
        self.save_visited()
        self.mapview.refresh_country(c)
        self.update_stats()
        self._update_selection_info()
        self._update_list_row(code)

    def toggle_selected(self):
        if self.sel_code:
            self.toggle_visited(self.sel_code)

    def show_on_map(self, code):
        c = self.by_code[code]
        self.open_map()
        self.mapview.select(c)
        self._update_selection_info()
        self.mapview.zoom_to(c)

    # ---- lista
    def set_filter(self, mode):
        self.filter_mode = mode
        self.refresh_list()

    def refresh_list(self, *a):
        q = fold(self.list_ids.search.text.strip())
        data = []
        for c in self.sorted_countries:
            v = c.id in self.visited
            if (self.filter_mode == "visited" and not v) or \
                    (self.filter_mode == "todo" and v):
                continue
            if q and q not in c.fold:
                continue
            data.append({"code": c.id, "name": c.name,
                         "subtitle": c.subtitle, "visited": v})
        self.list_ids.rv.data = data

    def _update_list_row(self, code):
        if self.filter_mode != "all":
            self.refresh_list()
            return
        rv = self.list_ids.rv
        for d in rv.data:
            if d["code"] == code:
                d["visited"] = code in self.visited
                rv.refresh_from_data()
                break

    # ---- nawigacja
    def open_list(self):
        self.refresh_list()
        self.sm.transition.direction = "left"
        self.sm.current = "list"

    def open_map(self):
        self.sm.transition.direction = "right"
        self.sm.current = "map"

    def _on_key(self, window, key, *args):
        if key == 27:  # przycisk „wstecz” na Androidzie / Esc
            if self.sm.current == "list":
                self.open_map()
                return True
            if self.mapview.selected is not None:
                self.mapview.select(None)
                self._update_selection_info()
                return True
        return False


if __name__ == "__main__":
    TravelMapApp().run()
