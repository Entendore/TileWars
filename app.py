#!/usr/bin/env python3
"""
Tile Wars — a territory conquest simulation (PySide6).

AI nations claim tiles on a generated island map. Every tick each nation:
  * grows troops based on the land (and cities) it holds (supply-capped),
  * spends troops to claim neutral tiles or conquer enemy tiles
    (defended tiles cost more the denser the defender's troops are),
  * may launch small naval invasions across one tile of water.

Run:  pip install PySide6
      python tile_wars.py
"""

import math
import random
import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt, QObject, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QPlainTextEdit, QPushButton, QSlider, QSpinBox,
                               QSizePolicy, QVBoxLayout, QWidget)

WATER, LAND = 0, 1
UNCLAIMED = -1

PALETTE = [
    ("Crimson", (225, 72, 70)),   ("Azure",  (66, 133, 244)),
    ("Verdant", (76, 190, 100)),  ("Amber",  (240, 190, 60)),
    ("Violet",  (168, 100, 230)), ("Coral",  (245, 130, 110)),
    ("Teal",    (38, 198, 190)),  ("Orchid", (230, 100, 190)),
    ("Slate",   (135, 148, 168)), ("Lime",   (160, 220, 60)),
    ("Copper",  (210, 130, 60)),  ("Indigo", (105, 110, 235)),
]

MAP_SIZES = {
    "Small  (96 × 60)":   (96, 60),
    "Medium (144 × 90)":  (144, 90),
    "Large  (192 × 120)": (192, 120),
}

STYLE = """
QMainWindow, QWidget { background-color: #12151c; color: #dce1ea; font-size: 13px; }
#TitleLabel { font-size: 24px; font-weight: 800; color: #f2b632; }
#SubLabel { color: #8d97a8; font-size: 11px; }
#StatsLabel { color: #f2b632; font-weight: 700; }
#HoverLabel { color: #8d97a8; font-size: 12px; }
QGroupBox { border: 1px solid #262c3a; border-radius: 10px; margin-top: 14px;
            padding: 10px 8px 8px 8px; font-weight: 700; color: #aeb7c6; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton { background-color: #24304a; border: 1px solid #33415f;
              border-radius: 8px; padding: 7px 10px; font-weight: 600; }
QPushButton:hover { background-color: #2d3c5e; }
QPushButton:pressed { background-color: #1c2537; }
QPushButton:disabled { color: #5b6270; background-color: #191e29; border-color: #232a3a; }
QSlider::groove:horizontal { height: 6px; background: #262c3a; border-radius: 3px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #f2b632; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #3d5a99; border-radius: 3px; }
QSpinBox, QComboBox { background: #1a2030; border: 1px solid #2c3550;
                      border-radius: 6px; padding: 4px 6px; }
QComboBox QAbstractItemView { background: #1a2030; selection-background-color: #2d3c5e; }
QListWidget { background: #161a24; border: 1px solid #262c3a; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 5px 6px; border-radius: 6px; }
QListWidget::item:selected { background: #2d3c5e; color: #ffffff; }
QPlainTextEdit { background: #10131a; border: 1px solid #262c3a; border-radius: 8px;
                 color: #9aa4b5; font-size: 11px; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #33415f;
                       border-radius: 4px; background: #1a2030; }
QCheckBox::indicator:checked { background: #f2b632; }
"""


@dataclass
class GameConfig:
    cols: int = 144
    rows: int = 90
    num_nations: int = 8
    num_cities: int = 14
    land_frac: float = 0.44
    # economy
    start_troops: float = 400.0
    growth_rate: float = 0.028        # fraction of troops gained per tick
    cap_base: float = 500.0
    cap_per_tile: float = 16.0        # max troops = base + tiles*k + cities*k
    cap_per_city: float = 450.0
    city_income: float = 10.0
    # combat
    neutral_cost: float = 2.0         # troops to claim a neutral tile
    density_cost_factor: float = 1.7  # enemy tile cost = 1 + defender_density * f
    defender_loss_factor: float = 0.6
    naval_cost: float = 14.0
    reserve_frac: float = 0.10
    min_reserve: float = 30.0


class Nation:
    __slots__ = ("id", "name", "color", "troops", "tile_count", "cities",
                 "capital", "alive", "aggression", "expansion", "kills")

    def __init__(self, nid, name, color, rng):
        self.id = nid
        self.name = name
        self.color = color
        self.troops = 0.0
        self.tile_count = 0
        self.cities = 0
        self.capital = None
        self.alive = True
        self.aggression = rng.uniform(0.45, 1.35)  # likes attacking enemies
        self.expansion = rng.uniform(0.70, 1.50)   # likes grabbing land fast
        self.kills = 0


class GameEngine(QObject):
    state_changed = Signal()
    event_logged = Signal(str)
    game_over = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = GameConfig()
        self.rng = random.Random()
        self.cols = self.rows = 0
        self.terrain = None
        self.owner = None
        self.city = None
        self.shade = None
        self.flash = None
        self.nations = []
        self.total_land = 0
        self.tick_n = 0
        self.over = False
        self.winner = None
        self.selected = None
        self._frontier = {}
        self._naval = {}

    # ------------------------------------------------------------- setup

    def new_game(self, cfg):
        self.cfg = cfg
        rng = self.rng
        cols, rows = cfg.cols, cfg.rows
        self.cols, self.rows = cols, rows
        self.tick_n = 0
        self.over = False
        self.winner = None
        self.selected = None
        self._frontier = {}
        self._naval = {}

        self.terrain = self._gen_terrain(cols, rows, cfg.land_frac, rng)
        self.owner = [[UNCLAIMED] * cols for _ in range(rows)]
        self.shade = [[rng.random() for _ in range(cols)] for _ in range(rows)]
        self.flash = [[-9] * cols for _ in range(rows)]
        self.city = [[False] * cols for _ in range(rows)]
        self.total_land = sum(row.count(LAND) for row in self.terrain)

        land = [(x, y) for y in range(rows) for x in range(cols)
                if self.terrain[y][x] == LAND]
        rng.shuffle(land)

        # cities, spaced apart
        placed = []
        min_d2 = (min(cols, rows) / 6.0) ** 2
        for (x, y) in land:
            if len(placed) >= cfg.num_cities:
                break
            if all((x - px) ** 2 + (y - py) ** 2 >= min_d2 for px, py in placed):
                placed.append((x, y))
                self.city[y][x] = True

        # capitals via farthest-point sampling → nations start spread out
        caps = [rng.choice(land)]
        while len(caps) < cfg.num_nations and len(caps) < len(land):
            best, best_d = None, -1.0
            for (x, y) in land:
                d = min((x - cx) ** 2 + (y - cy) ** 2 for cx, cy in caps)
                if d > best_d:
                    best_d, best = d, (x, y)
            caps.append(best)

        pool = PALETTE[:]
        rng.shuffle(pool)
        self.nations = []
        for i in range(cfg.num_nations):
            name, color = pool[i % len(pool)]
            n = Nation(i, name, color, rng)
            n.troops = cfg.start_troops
            n.capital = caps[i]
            self.nations.append(n)

        # small starting blob around each capital
        for n in self.nations:
            cx, cy = n.capital
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if dx * dx + dy * dy > 5:
                        continue
                    x, y = cx + dx, cy + dy
                    if (0 <= x < cols and 0 <= y < rows
                            and self.terrain[y][x] == LAND
                            and self.owner[y][x] == UNCLAIMED):
                        self.owner[y][x] = n.id

        for n in self.nations:
            n.tile_count = sum(row.count(n.id) for row in self.owner)
            n.cities = sum(1 for yy in range(rows) for xx in range(cols)
                           if self.city[yy][xx] and self.owner[yy][xx] == n.id)
        self.state_changed.emit()

    @staticmethod
    def _blur(g, cols, rows):
        out = [[0.0] * cols for _ in range(rows)]
        for y in range(rows):
            up = g[y - 1] if y else g[y]
            mid = g[y]
            dn = g[y + 1] if y < rows - 1 else g[y]
            for x in range(cols):
                x0 = x - 1 if x else 0
                x1 = x + 1 if x < cols - 1 else cols - 1
                out[y][x] = (up[x0] + up[x] + up[x1]
                             + mid[x0] + mid[x] + mid[x1]
                             + dn[x0] + dn[x] + dn[x1]) / 9.0
        return out

    def _gen_terrain(self, cols, rows, land_frac, rng):
        g = [[rng.random() for _ in range(cols)] for _ in range(rows)]
        for _ in range(3):
            g = self._blur(g, cols, rows)
        # push map edges underwater so it reads like a world map
        for y in range(rows):
            fy = abs(y / (rows - 1) * 2 - 1)
            for x in range(cols):
                fx = abs(x / (cols - 1) * 2 - 1)
                edge = max(fx, fy)
                if edge > 0.6:
                    g[y][x] -= (edge - 0.6) * 1.6
        flat = sorted(v for row in g for v in row)
        thr = flat[int((1.0 - land_frac) * (len(flat) - 1))]
        return [[LAND if v >= thr else WATER for v in row] for row in g]

    # ------------------------------------------------------------- loop

    def tick(self):
        if self.over or self.terrain is None:
            return
        self.tick_n += 1
        cfg = self.cfg

        # 1. economy: troops grow toward a supply cap set by territory
        for n in self.nations:
            if not n.alive:
                continue
            cap = (cfg.cap_base + n.tile_count * cfg.cap_per_tile
                   + n.cities * cfg.cap_per_city)
            income = 1 + n.troops * cfg.growth_rate + n.cities * cfg.city_income
            n.troops = min(cap, n.troops + income)

        # 2. one pass over the map: collect every nation's border targets
        fr, nv = {}, {}
        for n in self.nations:
            if n.alive and n.tile_count > 0:
                fr[n.id] = set()
                nv[n.id] = set()
        terrain, owner, cols, rows = self.terrain, self.owner, self.cols, self.rows
        for y in range(rows):
            orow, trow = owner[y], terrain[y]
            o_up = owner[y - 1] if y > 0 else None
            o_dn = owner[y + 1] if y < rows - 1 else None
            t_up = terrain[y - 1] if y > 0 else None
            t_dn = terrain[y + 1] if y < rows - 1 else None
            for x in range(cols):
                nid = orow[x]
                if nid < 0:
                    continue
                s = fr.get(nid)
                if s is None:
                    continue
                sea = nv[nid]
                # right
                if x + 1 < cols:
                    if trow[x + 1] == LAND:
                        if orow[x + 1] != nid:
                            s.add((x + 1, y))
                    elif x + 2 < cols and trow[x + 2] == LAND and orow[x + 2] != nid:
                        sea.add((x + 2, y))
                # left
                if x > 0:
                    if trow[x - 1] == LAND:
                        if orow[x - 1] != nid:
                            s.add((x - 1, y))
                    elif x > 1 and trow[x - 2] == LAND and orow[x - 2] != nid:
                        sea.add((x - 2, y))
                # down
                if y + 1 < rows:
                    if t_dn[x] == LAND:
                        if o_dn[x] != nid:
                            s.add((x, y + 1))
                    elif y + 2 < rows and terrain[y + 2][x] == LAND and owner[y + 2][x] != nid:
                        sea.add((x, y + 2))
                # up
                if y > 0:
                    if t_up[x] == LAND:
                        if o_up[x] != nid:
                            s.add((x, y - 1))
                    elif y > 1 and terrain[y - 2][x] == LAND and owner[y - 2][x] != nid:
                        sea.add((x, y - 1))
        self._frontier, self._naval = fr, nv

        # 3. nations act in random order each tick (fairness)
        order = [n for n in self.nations if n.alive and n.tile_count > 0]
        self.rng.shuffle(order)
        for n in order:
            if n.alive:
                self._nation_act(n)

        # 4. victory?
        alive = [n for n in self.nations if n.alive and n.tile_count > 0]
        if len(alive) == 1:
            a = alive[0]
            if a.tile_count >= self.total_land or (not fr.get(a.id) and not nv.get(a.id)):
                self.over = True
                self.winner = a
                pct = 100.0 * a.tile_count / max(1, self.total_land)
                self.log(f"🏆 {a.name} conquers the world! ({pct:.1f}% of all land)")
                self.game_over.emit(a.name)
        elif not alive:
            self.over = True
            self.log("💀 Every nation has fallen. The world is silent.")
            self.game_over.emit("")

        self.state_changed.emit()

    # ------------------------------------------------------------- AI

    def _nation_act(self, nat):
        cfg, rng = self.cfg, self.rng
        land_t = self._frontier.get(nat.id) or ()
        naval_t = self._naval.get(nat.id) or ()
        if not land_t and not naval_t:
            return
        reserve = max(cfg.min_reserve, nat.troops * cfg.reserve_frac)
        if nat.troops - reserve < cfg.neutral_cost:
            return
        max_attacks = max(1, int((1.5 + math.sqrt(nat.tile_count) * 1.4) * nat.expansion))

        scored = []
        for (x, y) in land_t:
            o = self.owner[y][x]
            adj = self._adjacent_owned(x, y, nat.id)
            if o == UNCLAIMED:
                cost = cfg.neutral_cost
                score = 1.6 * nat.expansion * (1 + 0.35 * adj) * rng.uniform(0.8, 1.25)
            else:
                d = self.nations[o]
                if not d.alive:
                    continue
                density = d.troops / max(1, d.tile_count)
                cost = 1.0 + density * cfg.density_cost_factor
                ratio = (nat.troops + 10.0) / (d.troops + 10.0)
                score = (nat.aggression * 2.4 * min(ratio, 2.5) * (1 + 0.30 * adj)
                         / (1 + density * 0.10) * rng.uniform(0.7, 1.3))
            scored.append((score, cost, x, y))
        for (x, y) in naval_t:
            o = self.owner[y][x]
            if o == UNCLAIMED:
                cost = cfg.naval_cost
                score = 1.1 * nat.expansion * rng.uniform(0.6, 1.1)
            else:
                d = self.nations[o]
                if not d.alive:
                    continue
                density = d.troops / max(1, d.tile_count)
                cost = cfg.naval_cost + 1.0 + density * cfg.density_cost_factor
                ratio = (nat.troops + 10.0) / (d.troops + 10.0)
                score = (nat.aggression * 1.2 * min(ratio, 2.5)
                         / (1 + density * 0.10) * rng.uniform(0.6, 1.1))
            scored.append((score, cost, x, y))
        if not scored:
            return
        scored.sort(key=lambda t: -t[0])

        attacks = tried = 0
        for score, cost, x, y in scored:
            if attacks >= max_attacks or tried >= 100:
                break
            tried += 1
            if nat.troops - reserve < cost:
                continue          # too expensive → try a cheaper target
            self._conquer(nat, x, y, cost)
            attacks += 1

    def _adjacent_owned(self, x, y, nid):
        c = 0
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < self.cols and 0 <= ny < self.rows and self.owner[ny][nx] == nid:
                c += 1
        return c

    def _conquer(self, nat, x, y, cost):
        nat.troops -= cost
        prev = self.owner[y][x]
        self.owner[y][x] = nat.id
        self.flash[y][x] = self.tick_n
        nat.tile_count += 1
        if self.city[y][x]:
            nat.cities += 1
            if prev != UNCLAIMED:
                self.nations[prev].cities -= 1
                self.log(f"🏛 {nat.name} seized a city from {self.nations[prev].name}!")
        if prev != UNCLAIMED:
            d = self.nations[prev]
            d.tile_count -= 1
            density = d.troops / max(1, d.tile_count)
            d.troops = max(0.0, d.troops - density * self.cfg.defender_loss_factor)
            if (x, y) == d.capital and d.tile_count > 0:
                self._relocate_capital(d, nat)
            if d.tile_count <= 0:
                d.alive = False
                nat.kills += 1
                self.log(f"⚔ {nat.name} eliminated {d.name}!")
                if self.selected == d.id:
                    self.selected = None

    def _relocate_capital(self, d, attacker):
        mine = [(x, y) for y in range(self.rows) for x in range(self.cols)
                if self.owner[y][x] == d.id]
        if not mine:
            return
        d.capital = self.rng.choice(mine)
        d.troops *= 0.7
        self.log(f"💥 {d.name}'s capital fell to {attacker.name}! Court relocated.")

    def log(self, msg):
        self.event_logged.emit(f"t{self.tick_n:>4} · {msg}")


class MapCanvas(QWidget):
    hover_info = Signal(str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.show_labels = True
        self._img = None
        self._buf = b""
        self._geom = (1.0, 0.0, 0.0)   # scale, offset x, offset y
        self.setMinimumSize(420, 300)
        self.setMouseTracking(True)
        engine.state_changed.connect(self.rebuild_image)

    # ------------------------------------------------------------ pixels
    def rebuild_image(self):
        e = self.engine
        if e.terrain is None:
            return
        cols, rows = e.cols, e.rows
        data = bytearray(cols * rows * 4)
        i = 0
        t = e.tick_n
        sel = e.selected
        terrain, owner = e.terrain, e.owner
        shade, flash, city = e.shade, e.flash, e.city
        ncolors = [n.color for n in e.nations]
        for y in range(rows):
            orow, trow = owner[y], terrain[y]
            srow, frow, crow = shade[y], flash[y], city[y]
            o_up = owner[y - 1] if y > 0 else None
            o_dn = owner[y + 1] if y < rows - 1 else None
            t_up = terrain[y - 1] if y > 0 else None
            t_dn = terrain[y + 1] if y < rows - 1 else None
            for x in range(cols):
                sh = 0.84 + 0.30 * srow[x]
                left = x > 0
                right = x < cols - 1
                if trow[x] == WATER:
                    r, g, b = 30.0 * sh, 74.0 * sh, 140.0 * sh
                    if ((right and trow[x + 1] == LAND)
                            or (left and trow[x - 1] == LAND)
                            or (t_dn is not None and t_dn[x] == LAND)
                            or (t_up is not None and t_up[x] == LAND)):
                        r *= 0.72; g *= 0.78; b *= 0.88      # coast shading
                else:
                    o = orow[x]
                    if o == UNCLAIMED:
                        r, g, b = 176.0 * sh, 164.0 * sh, 118.0 * sh
                    else:
                        cr, cg, cb = ncolors[o]
                        r, g, b = cr * sh, cg * sh, cb * sh
                        if sel is not None and o == sel:
                            r = min(255.0, r * 1.25)
                            g = min(255.0, g * 1.25)
                            b = min(255.0, b * 1.25)
                        # dark border where territory meets something else
                        border = ((not right) or (not left)
                                  or trow[x + 1] == WATER or orow[x + 1] != o
                                  or trow[x - 1] == WATER or orow[x - 1] != o
                                  or t_dn is None or t_dn[x] == WATER or o_dn[x] != o
                                  or t_up is None or t_up[x] == WATER or o_up[x] != o)
                        if border:
                            f = 0.45 if (sel is not None and o == sel) else 0.62
                            r *= f; g *= f; b *= f
                    if crow[x]:                              # city = gold tint
                        r = r * 0.55 + 114.0; g = g * 0.55 + 97.0; b = b * 0.55 + 36.0
                age = t - frow[x]                            # conquest flash
                if age == 0:
                    r += (255 - r) * 0.55; g += (255 - g) * 0.55; b += (255 - b) * 0.55
                elif age == 1:
                    r += (255 - r) * 0.22; g += (255 - g) * 0.22; b += (255 - b) * 0.22
                data[i] = int(r); data[i + 1] = int(g); data[i + 2] = int(b); data[i + 3] = 255
                i += 4
        # stamp capitals in white
        for n in e.nations:
            if n.alive and n.capital is not None:
                cx, cy = n.capital
                j = (cy * cols + cx) * 4
                data[j] = min(255, int(data[j] * 0.35 + 165))
                data[j + 1] = min(255, int(data[j + 1] * 0.35 + 165))
                data[j + 2] = min(255, int(data[j + 2] * 0.35 + 165))
        self._buf = bytes(data)
        self._img = QImage(self._buf, cols, rows, cols * 4, QImage.Format.Format_RGBA8888)
        self.update()

    # ------------------------------------------------------------ paint
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 12, 18))
        e = self.engine
        if self._img is None:
            p.setPen(QColor(150, 155, 170))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Press  🌍 New Game  to generate a world")
            return
        w, h = float(self.width()), float(self.height())
        cols, rows = e.cols, e.rows
        s = min(w / cols, h / rows)
        dw, dh = cols * s, rows * s
        ox, oy = (w - dw) / 2.0, (h - dh) / 2.0
        self._geom = (s, ox, oy)
        p.drawImage(QRectF(ox, oy, dw, dh), self._img)

        if self.show_labels and s >= 3.5:
            f = QFont(self.font())
            f.setBold(True)
            f.setPixelSize(int(max(9, min(18, s * 1.1))))
            p.setFont(f)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen_w = max(2.0, f.pixelSize() / 6.0)
            for n in e.nations:
                if not n.alive or n.capital is None:
                    continue
                cx = ox + (n.capital[0] + 0.5) * s
                cy = oy + (n.capital[1] + 0.5) * s
                text = f"{n.name} · {int(n.troops)}"      # live troop count on map
                path = QPainterPath()
                path.addText(QPointF(0, 0), f, text)
                br = path.boundingRect()
                path.translate(cx - br.width() / 2.0, cy - s * 1.8)
                p.setPen(QPen(QColor(0, 0, 0, 200), pen_w))
                p.setBrush(QColor(255, 244, 170) if n.id == e.selected
                           else QColor(255, 255, 255, 235))
                p.drawPath(path)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if e.over:
            p.fillRect(self.rect(), QColor(0, 0, 0, 120))
            f = QFont(self.font()); f.setBold(True); f.setPixelSize(28)
            p.setFont(f)
            p.setPen(QColor(255, 214, 92))
            if e.winner is not None:
                msg = (f"🏆  {e.winner.name} conquers the world!\n"
                       f"{e.winner.tile_count} tiles · ⚔ {int(e.winner.troops)} troops · "
                       f"{e.tick_n} ticks")
            else:
                msg = "💀  Every nation has fallen"
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)

    # ------------------------------------------------------------ mouse
    def _tile_at(self, pos):
        e = self.engine
        if e.terrain is None:
            return None
        s, ox, oy = self._geom
        x = int((pos.x() - ox) / s)
        y = int((pos.y() - oy) / s)
        if 0 <= x < e.cols and 0 <= y < e.rows:
            return x, y
        return None

    def mouseMoveEvent(self, ev):
        t = self._tile_at(ev.position())
        if t is None:
            self.hover_info.emit("")
            return
        x, y = t
        e = self.engine
        if e.terrain[y][x] == WATER:
            txt = f"🌊 Ocean ({x}, {y})"
        else:
            o = e.owner[y][x]
            if o == UNCLAIMED:
                base = "🟫 Neutral land"
            else:
                n = e.nations[o]
                base = (f"{n.name} — ⚔ {int(n.troops)} troops · {n.tile_count} tiles · "
                        f"🏛 {n.cities} cities")
                if n.capital == (x, y):
                    base += " · ★ capital"
            if e.city[y][x]:
                base += " · 🏛 city"
            txt = f"{base}   ({x}, {y})"
        self.hover_info.emit(txt)

    def mousePressEvent(self, ev):
        t = self._tile_at(ev.position())
        if t is None:
            return
        x, y = t
        e = self.engine
        o = e.owner[y][x]
        e.selected = None if (o == UNCLAIMED or o == e.selected) else o
        e.state_changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tile Wars · AI conquest")
        self.resize(1300, 820)
        self._icons = {}

        self.engine = GameEngine()
        self.engine.event_logged.connect(self.on_event)
        self.engine.game_over.connect(self.on_game_over)
        self.engine.state_changed.connect(self.refresh_leaderboard)
        self.engine.state_changed.connect(self.refresh_stats)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.engine.tick)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ----- map column
        left = QVBoxLayout()
        self.canvas = MapCanvas(self.engine)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.hover_info.connect(lambda s: self.hover_lbl.setText(s))
        left.addWidget(self.canvas, 1)
        self.hover_lbl = QLabel("Hover the map for tile info · click a nation to track it")
        self.hover_lbl.setObjectName("HoverLabel")
        left.addWidget(self.hover_lbl)
        root.addLayout(left, 1)

        # ----- sidebar
        side_widget = QWidget()
        side_widget.setFixedWidth(330)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        root.addWidget(side_widget)

        title = QLabel("TILE WARS")
        title.setObjectName("TitleLabel")
        sub = QLabel("AI nations claim tiles, grow armies and conquer the map")
        sub.setObjectName("SubLabel")
        sub.setWordWrap(True)
        side.addWidget(title)
        side.addWidget(sub)

        setup = QGroupBox("World setup")
        sl = QVBoxLayout(setup)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.size_combo = QComboBox()
        self.size_combo.addItems(list(MAP_SIZES.keys()))
        self.size_combo.setCurrentIndex(1)
        self.nations_spin = QSpinBox(); self.nations_spin.setRange(2, 12); self.nations_spin.setValue(8)
        self.cities_spin = QSpinBox(); self.cities_spin.setRange(0, 40); self.cities_spin.setValue(14)
        form.addRow("Map size", self.size_combo)
        form.addRow("Nations", self.nations_spin)
        form.addRow("Cities", self.cities_spin)
        sl.addLayout(form)
        self.new_btn = QPushButton("🌍  New Game")
        self.new_btn.clicked.connect(self.new_game)
        sl.addWidget(self.new_btn)
        side.addWidget(setup)

        playback = QGroupBox("Simulation")
        pv = QVBoxLayout(playback)
        row = QHBoxLayout()
        self.play_btn = QPushButton("⏸  Pause")
        self.play_btn.clicked.connect(self.toggle_play)
        self.step_btn = QPushButton("⏭  Step")
        self.step_btn.clicked.connect(self.engine.tick)
        row.addWidget(self.play_btn)
        row.addWidget(self.step_btn)
        pv.addLayout(row)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("🐢"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 12)
        self.speed_slider.setValue(5)
        self.speed_slider.valueChanged.connect(self.speed_changed)
        srow.addWidget(self.speed_slider, 1)
        srow.addWidget(QLabel("🐇"))
        pv.addLayout(srow)
        self.speed_lbl = QLabel("")
        pv.addWidget(self.speed_lbl)
        self.labels_chk = QCheckBox("Show nation labels on map")
        self.labels_chk.setChecked(True)
        self.labels_chk.toggled.connect(self.toggle_labels)
        pv.addWidget(self.labels_chk)
        side.addWidget(playback)

        lb = QGroupBox("Nations")
        lv = QVBoxLayout(lb)
        self.leader_list = QListWidget()
        self.leader_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.leader_list.itemClicked.connect(self.on_pick)
        lv.addWidget(self.leader_list)
        self.stats_lbl = QLabel("")
        self.stats_lbl.setObjectName("StatsLabel")
        self.stats_lbl.setWordWrap(True)
        lv.addWidget(self.stats_lbl)
        side.addWidget(lb, 1)

        lg = QGroupBox("Battle log")
        gv = QVBoxLayout(lg)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(400)
        self.log_box.setFixedHeight(150)
        gv.addWidget(self.log_box)
        side.addWidget(lg)

        self.speed_changed(self.speed_slider.value())
        self.new_game()   # start a world immediately

    # ------------------------------------------------------- actions
    def _interval(self):
        v = self.speed_slider.value()
        return max(22, int(620 / v))

    def speed_changed(self, v):
        self.speed_lbl.setText(f"Speed ×{v}  ({self._interval()} ms / tick)")
        if self.timer.isActive():
            self.timer.setInterval(self._interval())

    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("▶  Play")
        else:
            if self.engine.over:
                return
            self.timer.start(self._interval())
            self.play_btn.setText("⏸  Pause")

    def toggle_labels(self, on):
        self.canvas.show_labels = on
        self.canvas.update()

    def new_game(self):
        cols, rows = MAP_SIZES[self.size_combo.currentText()]
        cfg = GameConfig(cols=cols, rows=rows,
                         num_nations=self.nations_spin.value(),
                         num_cities=self.cities_spin.value())
        self.timer.stop()
        self.engine.new_game(cfg)
        self.log_box.clear()
        self.engine.log(f"🌍 New world: {cols}×{rows} · {cfg.num_nations} nations · "
                        f"{cfg.num_cities} cities · {self.engine.total_land} land tiles")
        self.timer.start(self._interval())
        self.play_btn.setText("⏸  Pause")
        self.play_btn.setEnabled(True)

    def on_pick(self, item):
        nid = item.data(Qt.ItemDataRole.UserRole)
        self.engine.selected = None if self.engine.selected == nid else nid
        self.engine.state_changed.emit()

    # ------------------------------------------------------- refresh
    def _icon_for(self, n):
        ic = self._icons.get(n.id)
        if ic is None:
            pm = QPixmap(12, 12)
            pm.fill(QColor(*n.color))
            ic = QIcon(pm)
            self._icons[n.id] = ic
        return ic

    def refresh_leaderboard(self):
        e = self.engine
        if not e.nations:
            return
        order = sorted(e.nations, key=lambda n: (not n.alive, -n.tile_count, -n.troops))
        lst = self.leader_list
        lst.blockSignals(True)
        lst.clear()
        for n in order:
            if n.alive:
                text = (f"{n.name}  ·  {n.tile_count} tiles  ·  "
                        f"⚔ {int(n.troops)}  ·  🏛 {n.cities}  ·  ☠{n.kills}")
            else:
                text = f"☠  {n.name} — eliminated"
            item = QListWidgetItem(self._icon_for(n), text)
            item.setData(Qt.ItemDataRole.UserRole, n.id)
            if not n.alive:
                item.setForeground(QColor(105, 112, 124))
            if e.selected == n.id:
                item.setSelected(True)
            lst.addItem(item)
        lst.blockSignals(False)

    def refresh_stats(self):
        e = self.engine
        if e.terrain is None:
            return
        owned = sum(n.tile_count for n in e.nations)
        pct = 100.0 * owned / max(1, e.total_land)
        leader = max(e.nations, key=lambda n: n.tile_count)
        self.stats_lbl.setText(
            f"Tick {e.tick_n} · land claimed {pct:.1f}%\n"
            f"Leader: {leader.name} ({leader.tile_count} tiles, ⚔ {int(leader.troops)})")

    def on_event(self, line):
        self.log_box.appendPlainText(line)

    def on_game_over(self, winner):
        self.timer.stop()
        self.play_btn.setText("🏁  Game over")
        self.play_btn.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Tile Wars")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()