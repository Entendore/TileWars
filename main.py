#!/usr/bin/env python3
"""
Tile Wars — a territory conquest simulation (PySide6).

AI nations claim tiles on a generated island map. Every tick each nation:
  * grows troops based on land & city value (supply-capped),
  * generates Build Points (BP) to construct Cities and Factories,
  * spends troops to claim neutral tiles or conquer enemy tiles,
  * evaluates strategic utility: investing in defense, mobilization, or building,
  * uses a "Spearhead" algorithm to focus attacks and push deep fronts.

Run:  pip install PySide6 opencv-python numpy
      python tile_wars.py
"""

import math
import random
import sys
from array import array
from dataclasses import dataclass

from PySide6.QtCore import Qt, QObject, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QPainter, QPainterPath,
                           QPen, QPixmap, QShortcut, QKeySequence)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressDialog, QPushButton,
                               QSlider, QSpinBox, QSizePolicy, QVBoxLayout, QWidget)

# Optional video export dependencies
try:
    import cv2
    import numpy as np
    VIDEO_EXPORT_ENABLED = True
except ImportError:
    VIDEO_EXPORT_ENABLED = False

# Biomes Constants
DEEP_OCEAN, OCEAN, BEACH, GRASS, FOREST, RAINFOREST, SAVANNA, DESERT, TUNDRA, SNOW, MOUNTAIN = range(11)
WATER_BIOMES = {DEEP_OCEAN, OCEAN}
UNCLAIMED = -1

BIOME_STATS = {
    DEEP_OCEAN: dict(name="Deep Ocean",   income=0.0, defense=0.0, tint=(15, 40, 90),   mod=(1.0, 1.0, 1.0)),
    OCEAN:      dict(name="Ocean",        income=0.0, defense=0.0, tint=(30, 74, 140),  mod=(1.0, 1.0, 1.0)),
    BEACH:      dict(name="Beach",        income=0.5, defense=0.8, tint=(230, 220, 160),mod=(1.2, 1.1, 0.8)),
    GRASS:      dict(name="Grassland",    income=1.0, defense=1.0, tint=(120, 160, 80), mod=(1.0, 1.0, 1.0)),
    FOREST:     dict(name="Forest",       income=0.8, defense=1.5, tint=(40, 100, 50),  mod=(0.6, 0.8, 0.5)),
    RAINFOREST: dict(name="Rainforest",   income=0.9, defense=1.8, tint=(20, 80, 30),   mod=(0.4, 0.7, 0.4)),
    SAVANNA:    dict(name="Savanna",      income=0.9, defense=1.0, tint=(180, 170, 80), mod=(1.1, 1.0, 0.7)),
    DESERT:     dict(name="Desert",       income=0.5, defense=0.8, tint=(220, 200, 120),mod=(1.2, 1.0, 0.5)),
    TUNDRA:     dict(name="Tundra",       income=0.4, defense=1.2, tint=(150, 160, 150),mod=(0.9, 0.9, 0.9)),
    SNOW:       dict(name="Snow",         income=0.1, defense=1.5, tint=(230, 240, 245),mod=(1.4, 1.4, 1.4)),
    MOUNTAIN:   dict(name="Mountain",     income=0.3, defense=2.5, tint=(130, 130, 130),mod=(0.8, 0.8, 0.8)),
}

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
    map_type: str = "Standard"
    # economy
    start_troops: float = 400.0
    growth_rate: float = 0.028
    cap_base: float = 500.0
    cap_per_tile: float = 16.0
    cap_per_city: float = 450.0
    city_income: float = 10.0
    factory_troop_bonus: float = 0.05
    factory_bp_bonus: float = 4.0
    # build costs
    city_cost_bp: float = 100.0
    factory_cost_bp: float = 150.0
    # combat
    neutral_cost: float = 2.0
    density_cost_factor: float = 1.7
    defender_loss_factor: float = 0.6
    naval_cost: float = 14.0
    reserve_frac: float = 0.10
    min_reserve: float = 30.0
    # AI personality ranges
    aggression_lo: float = 0.45
    aggression_hi: float = 1.35
    expansion_lo: float = 0.70
    expansion_hi: float = 1.50


class Nation:
    __slots__ = ("id", "name", "color", "troops", "tile_count", "cities", "factories",
                 "bp", "alive", "aggression", "expansion", "kills",
                 "defensive", "peak_tiles", "peak_tick", "biome_value",
                 "defense_level", "mobilize_timer", "label_x", "label_y")

    def __init__(self, nid, name, color, cfg, rng):
        self.id = nid
        self.name = name
        self.color = color
        self.troops = 0.0
        self.tile_count = 0
        self.cities = 0
        self.factories = 0
        self.bp = 0.0
        self.alive = True
        self.aggression = rng.uniform(cfg.aggression_lo, cfg.aggression_hi)
        self.expansion = rng.uniform(cfg.expansion_lo, cfg.expansion_hi)
        self.defensive = rng.uniform(0.4, 1.2)
        self.kills = 0
        self.peak_tiles = 0
        self.peak_tick = 0
        self.biome_value = 0.0
        self.defense_level = 0
        self.mobilize_timer = 0
        self.label_x = 0.0
        self.label_y = 0.0


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
        self.factory = None
        self.shade = None
        self.flash = None
        self.nations = []
        self.total_land = 0
        self.tick_n = 0
        self.over = False
        self.winner = None
        self.selected = None
        self.heatmap = False
        self._frontier = {}
        self._naval = {}
        self._color_lut = None
        self.city_coords = []
        self.factory_coords = []

    def _idx(self, x, y):
        return y * self.cols + x

    def _in_bounds(self, x, y):
        return 0 <= x < self.cols and 0 <= y < self.rows

    def new_game(self, cfg):
        self.cfg = cfg
        rng = self.rng
        cols, rows = cfg.cols, cfg.rows
        self.cols, self.rows = cols, rows
        self.tick_n = 0
        self.over = False
        self.winner = None
        self.selected = None
        self.heatmap = False
        self._frontier = {}
        self._naval = {}

        n_cells = cols * rows
        self.terrain = self._gen_terrain(cols, rows, cfg.land_frac, rng, cfg.map_type)
        self.owner = array('i', [UNCLAIMED] * n_cells)
        self.shade = array('d', [rng.random() for _ in range(n_cells)])
        self.flash = array('i', [-9] * n_cells)
        self.city = bytearray(n_cells)
        self.factory = bytearray(n_cells)
        self.total_land = sum(1 for b in self.terrain if b not in WATER_BIOMES)

        land_idx = [i for i, v in enumerate(self.terrain) if v not in WATER_BIOMES]
        rng.shuffle(land_idx)
        land_pts = [(i % cols, i // cols) for i in land_idx]

        placed = []
        min_d2 = (min(cols, rows) / 6.0) ** 2
        for (x, y) in land_pts:
            if len(placed) >= cfg.num_cities:
                break
            if all((x - px) ** 2 + (y - py) ** 2 >= min_d2 for px, py in placed):
                placed.append((x, y))
                self.city[self._idx(x, y)] = 1

        starts = [rng.choice(land_pts)]
        while len(starts) < cfg.num_nations and len(starts) < len(land_pts):
            best, best_d = None, -1.0
            for (x, y) in land_pts:
                d = min((x - cx) ** 2 + (y - cy) ** 2 for cx, cy in starts)
                if d > best_d:
                    best_d, best = d, (x, y)
            starts.append(best)

        pool = PALETTE[:]
        rng.shuffle(pool)
        self.nations = []
        for i in range(cfg.num_nations):
            name, color = pool[i % len(pool)]
            n = Nation(i, name, color, cfg, rng)
            n.troops = cfg.start_troops
            sx, sy = starts[i]
            self.city[self._idx(sx, sy)] = 1
            self.nations.append(n)

        self._color_lut = [(0, 0, 0)] * (len(self.nations) + 1)
        for n in self.nations:
            self._color_lut[n.id] = n.color

        for n_idx, n in enumerate(self.nations):
            sx, sy = starts[n_idx]
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if dx * dx + dy * dy > 5:
                        continue
                    x, y = sx + dx, sy + dy
                    if self._in_bounds(x, y) and self.terrain[self._idx(x, y)] not in WATER_BIOMES \
                            and self.owner[self._idx(x, y)] == UNCLAIMED:
                        self.owner[self._idx(x, y)] = n.id

        self._recount_nations()
        self.state_changed.emit()

    def _recount_nations(self):
        counts = [0] * len(self.nations)
        city_counts = [0] * len(self.nations)
        fac_counts = [0] * len(self.nations)
        b_vals = [0.0] * len(self.nations)
        sum_x = [0] * len(self.nations)
        sum_y = [0] * len(self.nations)
        
        self.city_coords.clear()
        self.factory_coords.clear()
        
        for i, o in enumerate(self.owner):
            if o >= 0:
                counts[o] += 1
                b_vals[o] += BIOME_STATS[self.terrain[i]]['income']
                y, x = divmod(i, self.cols)
                if self.city[i]:
                    city_counts[o] += 1
                    self.city_coords.append((x, y))
                if self.factory[i]:
                    fac_counts[o] += 1
                    self.factory_coords.append((x, y))
                sum_x[o] += x
                sum_y[o] += y
                
        for n in self.nations:
            n.tile_count = counts[n.id]
            n.cities = city_counts[n.id]
            n.factories = fac_counts[n.id]
            n.biome_value = b_vals[n.id]
            if n.tile_count > 0:
                n.label_x = sum_x[n.id] / n.tile_count
                n.label_y = sum_y[n.id] / n.tile_count
            if n.tile_count > n.peak_tiles:
                n.peak_tiles = n.tile_count
                n.peak_tick = self.tick_n

    @staticmethod
    def _fbm(cols, rows, rng, scale=8.0, octaves=4):
        def fade(t): return t * t * t * (t * (t * 6 - 15) + 10)
        def lerp(a, b, t): return a + (b - a) * t
        
        grids = []
        gw = max(2, int(cols / scale) + 2)
        gh = max(2, int(rows / scale) + 2)
        for o in range(octaves):
            grids.append([[rng.random() for _ in range(gw)] for _ in range(gh)])
            gw = max(2, int(gw * 2))
            gh = max(2, int(gh * 2))
            
        out = [0.0] * (cols * rows)
        amplitude = 1.0
        total_amp = 0.0
        
        for o in range(octaves):
            grid = grids[o]
            g_w = len(grid[0])
            g_h = len(grid)
            for y in range(rows):
                gy = (y / (rows - 1)) * (g_h - 1)
                y0 = int(gy)
                y1 = min(y0 + 1, g_h - 1)
                dy = fade(gy - y0)
                for x in range(cols):
                    gx = (x / (cols - 1)) * (g_w - 1)
                    x0 = int(gx)
                    x1 = min(x0 + 1, g_w - 1)
                    dx = fade(gx - x0)
                    v00 = grid[y0][x0]; v01 = grid[y0][x1]
                    v10 = grid[y1][x0]; v11 = grid[y1][x1]
                    v0 = lerp(v00, v01, dx)
                    v1 = lerp(v10, v11, dx)
                    out[y * cols + x] += lerp(v0, v1, dy) * amplitude
            amplitude *= 0.5
            total_amp += amplitude
            
        for i in range(cols * rows): out[i] /= total_amp
        return out

    def _gen_terrain(self, cols, rows, land_frac, rng, map_type="Standard"):
        elev = self._fbm(cols, rows, rng, scale=8.0, octaves=5)
        moist = self._fbm(cols, rows, rng, scale=6.0, octaves=4)
        temp_noise = self._fbm(cols, rows, rng, scale=12.0, octaves=3)
        
        if map_type == "Transverse Oceans":
            for y in range(rows):
                for x in range(cols):
                    idx = y * cols + x
                    v1 = abs(x / cols - 0.33) < 0.05 + math.sin(y / rows * math.pi * 3) * 0.03
                    v2 = abs(x / cols - 0.66) < 0.05 + math.sin(y / rows * math.pi * 3) * 0.03
                    h1 = abs(y / rows - 0.5) < 0.05 + math.sin(x / cols * math.pi * 4) * 0.03
                    if v1 or v2 or h1:
                        elev[idx] -= 0.4
        
        sorted_elev = sorted(elev)
        sea_level = sorted_elev[int(land_frac * len(sorted_elev))]
        terrain = array('b', [DEEP_OCEAN] * (cols * rows))
        
        for y in range(rows):
            lat = abs(y / (rows - 1) - 0.5) * 2
            base_temp = 1.0 - lat * 1.2
            for x in range(cols):
                idx = y * cols + x
                e = elev[idx]
                m = moist[idx]
                t = max(0.0, min(1.0, base_temp - e * 0.4 + (temp_noise[idx] - 0.5) * 0.3))
                
                if map_type == "Extreme Biomes":
                    t = max(0.0, min(1.0, (t - 0.5) * 1.6 + 0.5))
                    m = max(0.0, min(1.0, (m - 0.5) * 1.6 + 0.5))
                
                if e < sea_level:
                    if e < sea_level - (sea_level * 0.4):
                        terrain[idx] = DEEP_OCEAN
                    else:
                        terrain[idx] = OCEAN
                else:
                    rel_e = (e - sea_level) / max(0.01, 1.0 - sea_level)
                    if rel_e > 0.75 and t < 0.35: terrain[idx] = SNOW
                    elif rel_e > 0.80: terrain[idx] = MOUNTAIN
                    elif rel_e < 0.05: terrain[idx] = BEACH
                    elif t < 0.25: terrain[idx] = TUNDRA
                    elif t < 0.45 and m > 0.55: terrain[idx] = FOREST
                    elif t < 0.45: terrain[idx] = TUNDRA
                    elif m < 0.25: terrain[idx] = DESERT
                    elif m < 0.40 and t > 0.65: terrain[idx] = SAVANNA
                    elif m > 0.65 and t > 0.65: terrain[idx] = RAINFOREST
                    elif m > 0.50: terrain[idx] = FOREST
                    else: terrain[idx] = GRASS
        return terrain

    def tick(self):
        if self.over or self.terrain is None: return
        self.tick_n += 1
        cfg = self.cfg

        for n in self.nations:
            if not n.alive: continue
            if n.mobilize_timer > 0: n.mobilize_timer -= 1
            
            cap = (cfg.cap_base + n.biome_value * cfg.cap_per_tile + n.cities * cfg.cap_per_city)
            income = 1 + n.troops * cfg.growth_rate + n.cities * cfg.city_income
            income *= (1.0 + n.factories * cfg.factory_troop_bonus)
            n.troops = min(cap, n.troops + income)

            bp_income = 1.0 + n.tile_count * 0.1 + n.cities * 0.5 + n.factories * cfg.factory_bp_bonus
            n.bp += bp_income

        fr, nv = self._collect_frontiers()
        self._frontier, self._naval = fr, nv

        alive = [n for n in self.nations if n.alive and n.tile_count > 0]
        if not alive:
            self.over = True
            self.log("💀 Every nation has fallen. The world is silent.")
            self.game_over.emit("")
            self.state_changed.emit()
            return
        leader = max(alive, key=lambda n: n.tile_count)
        leader_threshold = leader.tile_count * 0.85

        order = list(alive)
        self.rng.shuffle(order)
        for n in order:
            if n.alive:
                self._nation_act(n, leader if n.tile_count < leader_threshold else None)

        alive = [n for n in self.nations if n.alive and n.tile_count > 0]
        if len(alive) == 1:
            a = alive[0]
            # Absolute Victory: Taking EVERY land tile
            if a.tile_count >= self.total_land:
                self.over = True
                self.winner = a
                self.log(f"🏆 {a.name} has taken every tile and conquers the world!")
                self.game_over.emit(a.name)
            else:
                # Fallback victory: no targets left to attack
                no_targets = not fr.get(a.id) and not nv.get(a.id)
                if no_targets:
                    self.over = True
                    self.winner = a
                    pct = 100.0 * a.tile_count / max(1, self.total_land)
                    self.log(f"🏆 {a.name} conquers the world! ({pct:.1f}% of all land)")
                    self.game_over.emit(a.name)
        elif not alive:
            self.over = True
            self.log("💀 Every nation has fallen. The world is silent.")
            self.game_over.emit("")

        self._recount_nations()
        self.state_changed.emit()

    def _collect_frontiers(self):
        fr, nv = {}, {}
        for n in self.nations:
            if n.alive and n.tile_count > 0:
                fr[n.id] = set()
                nv[n.id] = set()
        cols, rows = self.cols, self.rows
        terrain, owner = self.terrain, self.owner
        for y in range(rows):
            base = y * cols
            up_base = (y - 1) * cols if y > 0 else -1
            dn_base = (y + 1) * cols if y < rows - 1 else -1
            for x in range(cols):
                i = base + x
                nid = owner[i]
                if nid < 0: continue
                s = fr.get(nid)
                if s is None: continue
                sea = nv[nid]
                
                if x + 1 < cols:
                    ir = i + 1
                    if terrain[ir] not in WATER_BIOMES:
                        if owner[ir] != nid: s.add((x + 1, y))
                    elif x + 2 < cols:
                        ir2 = i + 2
                        if terrain[ir2] not in WATER_BIOMES and owner[ir2] != nid: sea.add((x + 2, y))
                if x > 0:
                    il = i - 1
                    if terrain[il] not in WATER_BIOMES:
                        if owner[il] != nid: s.add((x - 1, y))
                    elif x > 1:
                        il2 = i - 2
                        if terrain[il2] not in WATER_BIOMES and owner[il2] != nid: sea.add((x - 2, y))
                if dn_base >= 0:
                    idn = dn_base + x
                    if terrain[idn] not in WATER_BIOMES:
                        if owner[idn] != nid: s.add((x, y + 1))
                    elif y + 2 < rows:
                        idn2 = (y + 2) * cols + x
                        if terrain[idn2] not in WATER_BIOMES and owner[idn2] != nid: sea.add((x, y + 2))
                if up_base >= 0:
                    iup = up_base + x
                    if terrain[iup] not in WATER_BIOMES:
                        if owner[iup] != nid: s.add((x, y - 1))
                    elif y > 1:
                        iup2 = (y - 2) * cols + x
                        if terrain[iup2] not in WATER_BIOMES and owner[iup2] != nid: sea.add((x, y - 2))
        return fr, nv

    def _assess_threat(self, nat):
        own_borders = self._frontier.get(nat.id) or ()
        if not own_borders: return 0.0
        enemy_strength = 0.0
        seen = set()
        for (x, y) in own_borders:
            o = self.owner[self._idx(x, y)]
            if o != UNCLAIMED and o not in seen:
                seen.add(o)
                enemy_strength += self.nations[o].troops
        if enemy_strength <= 0: return 0.0
        return min(1.0, (enemy_strength / max(1.0, nat.troops)) / 3.0)

    def _nation_act(self, nat, coalition_target):
        cfg, rng = self.cfg, self.rng
        threat = self._assess_threat(nat)
        self._evaluate_strategic_actions(nat, threat)

        land_t = self._frontier.get(nat.id) or ()
        naval_t = self._naval.get(nat.id) or ()
        if not land_t and not naval_t: return

        base_reserve = max(cfg.min_reserve, nat.troops * cfg.reserve_frac)
        threat_reserve = nat.troops * threat * 0.30 * nat.defensive
        reserve = base_reserve + threat_reserve

        usable_troops = nat.troops - reserve
        if usable_troops < cfg.neutral_cost: return

        eff_exp = nat.expansion * (1.3 if nat.mobilize_timer > 0 else 1.0)
        base_attacks = 1.5 + math.sqrt(nat.tile_count) * 1.4
        
        wealth_mult = 1.0 + (usable_troops / 120.0)
        wealth_mult = min(wealth_mult, 5.0) 
        
        max_attacks = max(1, int(base_attacks * eff_exp * wealth_mult))
        max_attacks = min(max_attacks, 80) 

        scored = []
        for (x, y) in land_t:
            i = self._idx(x, y)
            o = self.owner[i]
            adj = self._adjacent_owned(x, y, nat.id)
            biome = self.terrain[i]
            b_def = BIOME_STATS[biome]['defense']
            city_bonus = 2.2 if self.city[i] else 1.4 if any(self._in_bounds(x+dx, y+dy) and self.city[self._idx(x+dx, y+dy)] for dx, dy in ((1,0),(-1,0),(0,1),(0,-1))) else 1.0

            if o == UNCLAIMED:
                cost = cfg.neutral_cost * b_def
                score = 1.6 * eff_exp * (1 + 0.35 * adj) * city_bonus * rng.uniform(0.8, 1.25)
            else:
                d = self.nations[o]
                if not d.alive: continue
                density = d.troops / max(1, d.tile_count)
                cost = (1.0 + density * cfg.density_cost_factor) * b_def * (1.0 + d.defense_level * 0.15)
                ratio = (nat.troops + 10.0) / (d.troops + 10.0)
                coalition_bonus = 1.5 if d is coalition_target else 1.0
                score = (nat.aggression * 2.4 * min(ratio, 2.5) * (1 + 0.30 * adj)
                         * city_bonus * coalition_bonus
                         / (1 + density * 0.10) * rng.uniform(0.7, 1.3))
            
            if cost <= 0: cost = 0.1
            efficiency = score / cost
            scored.append((efficiency, score, cost, x, y))

        if len(land_t) < 4 or coalition_target is not None or (nat.aggression > 1.1 and usable_troops > reserve * 1.5):
            for (x, y) in naval_t:
                i = self._idx(x, y)
                o = self.owner[i]
                biome = self.terrain[i]
                b_def = BIOME_STATS[biome]['defense']
                if o == UNCLAIMED:
                    cost = cfg.naval_cost * b_def
                    score = 1.1 * eff_exp * rng.uniform(0.6, 1.1)
                else:
                    d = self.nations[o]
                    if not d.alive: continue
                    density = d.troops / max(1, d.tile_count)
                    cost = cfg.naval_cost * b_def + 1.0 + density * cfg.density_cost_factor
                    ratio = (nat.troops + 10.0) / (d.troops + 10.0)
                    coalition_bonus = 1.6 if d is coalition_target else 0.8
                    score = (nat.aggression * 1.2 * min(ratio, 2.5) * coalition_bonus / (1 + density * 0.10) * rng.uniform(0.6, 1.1))
                
                if cost <= 0: cost = 0.1
                efficiency = score / cost
                scored.append((efficiency, score, cost, x, y))

        if not scored: return

        scored.sort(key=lambda t: t[1], reverse=True) 
        spearhead_x, spearhead_y = scored[0][3], scored[0][4]
        max_dist = math.sqrt(self.cols**2 + self.rows**2) * 0.3 
        
        biased_scored = []
        for eff, score, cost, x, y in scored:
            dist = math.hypot(x - spearhead_x, y - spearhead_y)
            proximity_mult = 1.0 + 2.0 * (1.0 - min(1.0, dist / max_dist))
            biased_eff = eff * proximity_mult
            biased_scored.append((biased_eff, score, cost, x, y))
            
        biased_scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

        attacks = tried = 0
        for eff, score, cost, x, y in biased_scored:
            if attacks >= max_attacks or tried >= 150: break
            tried += 1
            if nat.troops - reserve < cost: continue
            
            if usable_troops < reserve * 1.5 and eff < 0.15:
                continue
                
            self._conquer(nat, x, y, cost)
            attacks += 1

    def _evaluate_strategic_actions(self, nat, threat):
        cfg = self.cfg
        cap = (cfg.cap_base + nat.biome_value * cfg.cap_per_tile + nat.cities * cfg.cap_per_city)
        troop_ratio = nat.troops / max(1.0, cap)

        found_util = 0.0
        if nat.bp >= cfg.city_cost_bp:
            found_util = 0.8 + (1.0 - nat.cities / 10.0) * 0.5 - threat * 0.4
            max_cities = max(2, nat.tile_count // 25)
            if nat.cities >= max_cities: found_util = 0.0

        fac_util = 0.0
        if nat.bp >= cfg.factory_cost_bp and nat.cities > 0:
            fac_util = 0.7 + (1.0 - nat.factories / max(1, nat.cities)) * 0.5 - threat * 0.3
            max_facs = max(1, nat.cities * 2)
            if nat.factories >= max_facs: fac_util = 0.0

        def_cost = 500 * (1 + nat.defense_level)
        def_util = 0.0
        if nat.troops > def_cost + 300 and troop_ratio > 0.4:
            def_util = 0.5 + threat * 1.5 + (0.3 if troop_ratio > 0.75 else 0.0)

        mob_cost = 400
        mob_util = 0.0
        if nat.mobilize_timer == 0 and nat.troops > mob_cost + 400 and troop_ratio > 0.5:
            mob_util = 0.4 + nat.aggression * 0.5 - threat * 0.8 + (0.3 if troop_ratio > 0.8 else 0.0)

        actions = [
            (found_util, 'found', cfg.city_cost_bp),
            (fac_util, 'fac', cfg.factory_cost_bp),
            (def_util, 'def', def_cost),
            (mob_util, 'mob', mob_cost)
        ]
        actions.sort(key=lambda x: -x[0])
        best_util, best_act, best_cost = actions[0]

        if best_util > 0.85:
            if best_act == 'found':
                nat.bp -= best_cost
                self._found_city(nat)
                self.log(f"🏗 {nat.name} founded a new city! (Total: {nat.cities})")
            elif best_act == 'fac':
                nat.bp -= best_cost
                self._build_factory(nat)
                self.log(f"🏭 {nat.name} built a factory! (Total: {nat.factories})")
            elif best_act == 'def':
                nat.troops -= best_cost
                nat.defense_level += 1
                self.log(f"🛡 {nat.name} fortifies defenses (Def Lv.{nat.defense_level})")
            elif best_act == 'mob':
                nat.troops -= best_cost
                nat.mobilize_timer = 30
                self.log(f"⚔ {nat.name} mobilizes for war! (+Exp, -Def for 30 ticks)")

    def _found_city(self, nat):
        candidates = []
        cols = self.cols
        for i, o in enumerate(self.owner):
            if o == nat.id and not self.city[i] and not self.factory[i]:
                biome = self.terrain[i]
                if biome in (GRASS, FOREST, SAVANNA):
                    x, y = i % cols, i // cols
                    if self._adjacent_owned(x, y, nat.id) == 4:
                        candidates.append(i)
        if candidates:
            idx = self.rng.choice(candidates)
            self.city[idx] = 1
            nat.cities += 1

    def _build_factory(self, nat):
        candidates = []
        cols = self.cols
        for i, o in enumerate(self.owner):
            if o == nat.id and not self.factory[i] and not self.city[i]:
                biome = self.terrain[i]
                if biome in (GRASS, SAVANNA, DESERT, BEACH):
                    x, y = i % cols, i // cols
                    if self._adjacent_owned(x, y, nat.id) == 4:
                        candidates.append(i)
        if candidates:
            idx = self.rng.choice(candidates)
            self.factory[idx] = 1
            nat.factories += 1

    def _adjacent_owned(self, x, y, nid):
        c = 0
        cols = self.cols
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self._in_bounds(nx, ny) and self.owner[ny * cols + nx] == nid:
                c += 1
        return c

    def _conquer(self, nat, x, y, cost):
        nat.troops -= cost
        i = self._idx(x, y)
        prev = self.owner[i]
        biome = self.terrain[i]
        b_def = BIOME_STATS[biome]['defense']
        b_inc = BIOME_STATS[biome]['income']

        self.owner[i] = nat.id
        self.flash[i] = self.tick_n
        nat.tile_count += 1
        nat.biome_value += b_inc
        
        if nat.tile_count > nat.peak_tiles:
            nat.peak_tiles = nat.tile_count
            nat.peak_tick = self.tick_n

        if self.city[i]:
            nat.cities += 1
            if prev != UNCLAIMED:
                self.nations[prev].cities -= 1
                self.log(f"🏛 {nat.name} seized a city from {self.nations[prev].name}!")

        if self.factory[i]:
            nat.factories += 1
            if prev != UNCLAIMED:
                self.nations[prev].factories -= 1
                self.log(f"🏭 {nat.name} captured a factory from {self.nations[prev].name}!")

        if prev != UNCLAIMED:
            d = self.nations[prev]
            d.tile_count -= 1
            d.biome_value -= b_inc
            density = d.troops / max(1, d.tile_count)
            
            def_mult = b_def * (1.0 + d.defense_level * 0.2) * (0.8 if d.mobilize_timer > 0 else 1.0)
            defender_loss = (density * 0.5 + cost * 0.8) * self.cfg.defender_loss_factor * def_mult
            d.troops = max(0.0, d.troops - defender_loss)
            
            if d.tile_count <= 0:
                d.alive = False
                nat.kills += 1
                self.log(f"☠ {nat.name} eliminated {d.name}!")
                if self.selected == d.id:
                    self.selected = None

    def log(self, msg):
        self.event_logged.emit(f"t{self.tick_n:>4} · {msg}")


class MapCanvas(QWidget):
    hover_info = Signal(str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.show_labels = True
        self.show_grid = False
        self._img = None
        self._buf = b""
        self._geom = (1.0, 0.0, 0.0)
        self.setMinimumSize(420, 300)
        self.setMouseTracking(True)
        engine.state_changed.connect(self.rebuild_image)

    def rebuild_image(self):
        e = self.engine
        if e.terrain is None: return
        cols, rows = e.cols, e.rows
        data = bytearray(cols * rows * 4)
        i = 0
        t = e.tick_n
        sel = e.selected
        heatmap = e.heatmap
        terrain, owner = e.terrain, e.owner
        shade, flash, city, factory = e.shade, e.flash, e.city, e.factory
        lut = e._color_lut
        nations = e.nations

        def clamp_byte(v):
            iv = int(v)
            return iv if 0 <= iv <= 255 else (0 if iv < 0 else 255)

        for y in range(rows):
            base = y * cols
            up_base = (y - 1) * cols if y > 0 else -1
            dn_base = (y + 1) * cols if y < rows - 1 else -1
            for x in range(cols):
                idx = base + x
                sh = 0.84 + 0.30 * shade[idx]
                left = x > 0
                right = x < cols - 1
                biome = terrain[idx]
                b_stats = BIOME_STATS[biome]
                
                if biome in WATER_BIOMES:
                    r, g, b = b_stats['tint'][0] * sh, b_stats['tint'][1] * sh, b_stats['tint'][2] * sh
                    if biome == OCEAN and ((right and terrain[idx + 1] not in WATER_BIOMES)
                            or (left and terrain[idx - 1] not in WATER_BIOMES)
                            or (dn_base >= 0 and terrain[dn_base + x] not in WATER_BIOMES)
                            or (up_base >= 0 and terrain[up_base + x] not in WATER_BIOMES)):
                        r *= 1.4; g *= 1.4; b *= 1.4
                else:
                    o = owner[idx]
                    mod_r, mod_g, mod_b = b_stats['mod']
                    if o == UNCLAIMED:
                        tr, tg, tb = b_stats['tint']
                        r, g, b = tr * sh, tg * sh, tb * sh
                    else:
                        cr, cg, cb = lut[o]
                        r, g, b = cr * sh * mod_r, cg * sh * mod_g, cb * sh * mod_b
                        r = min(255.0, r); g = min(255.0, g); b = min(255.0, b)
                        
                        if heatmap:
                            n = nations[o]
                            dens = min(1.0, n.troops / max(1.0, n.tile_count * 4.0))
                            r *= 0.5 + 0.7 * dens; g *= 0.5 + 0.7 * dens; b *= 0.5 + 0.7 * dens
                        
                        if sel is not None and o == sel:
                            r = min(255.0, r * 1.25); g = min(255.0, g * 1.25); b = min(255.0, b * 1.25)
                        
                        border = ((not right) or (not left)
                                  or terrain[idx + 1] in WATER_BIOMES or owner[idx + 1] != o
                                  or terrain[idx - 1] in WATER_BIOMES or owner[idx - 1] != o
                                  or dn_base < 0 or terrain[dn_base + x] in WATER_BIOMES or owner[dn_base + x] != o
                                  or up_base < 0 or terrain[up_base + x] in WATER_BIOMES or owner[up_base + x] != o)
                        if border:
                            f = 0.45 if (sel is not None and o == sel) else 0.62
                            r *= f; g *= f; b *= f

                    if city[idx]:
                        r = r * 0.55 + 114.0; g = g * 0.55 + 97.0; b = b * 0.55 + 36.0
                    elif factory[idx]:
                        r = r * 0.45 + 120.0; g = g * 0.45 + 40.0; b = b * 0.45 + 30.0

                age = t - flash[idx]
                if age == 0:
                    r += (255 - r) * 0.55; g += (255 - g) * 0.55; b += (255 - b) * 0.55
                elif age == 1:
                    r += (255 - r) * 0.30; g += (255 - g) * 0.30; b += (255 - b) * 0.30
                elif age == 2:
                    r += (255 - r) * 0.12; g += (255 - g) * 0.12; b += (255 - b) * 0.12

                data[i] = clamp_byte(r)
                data[i + 1] = clamp_byte(g)
                data[i + 2] = clamp_byte(b)
                data[i + 3] = 255
                i += 4

        self._buf = bytes(data)
        self._img = QImage(self._buf, cols, rows, cols * 4, QImage.Format.Format_RGBA8888)
        self.update()

    def render_video_frame(self, width, height, is_shorts):
        img = QImage(width, height, QImage.Format.Format_RGBA8888)
        img.fill(QColor(18, 21, 28))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        f = QFont("Arial", 40, QFont.Bold)
        p.setPen(QColor(242, 182, 50))
        p.setFont(f)
        p.drawText(50, 80, "TILE WARS")
        
        e = self.engine
        f2 = QFont("Arial", 20)
        p.setFont(f2)
        p.setPen(QColor(141, 151, 168))
        owned = sum(n.tile_count for n in e.nations)
        pct = 100.0 * owned / max(1, e.total_land)
        p.drawText(50, 115, f"Tick {e.tick_n}  |  Land: {pct:.1f}%")
        
        if self._img is not None:
            if is_shorts:
                map_w, map_h = 1000, 900
                map_x, map_y = 40, 150
            else:
                map_w, map_h = 1200, 950
                map_x, map_y = 40, 150
            
            src_w, src_h = self._img.width(), self._img.height()
            scale = min(map_w / src_w, map_h / src_h)
            dw, dh = int(src_w * scale), int(src_h * scale)
            dx = map_x + (map_w - dw) // 2
            dy = map_y + (map_h - dh) // 2
            p.drawImage(QRectF(dx, dy, dw, dh), self._img)
            
            bar_y = dy + dh + 20
            p.setPen(QPen(QColor(0, 0, 0, 0)))
            p.setBrush(QColor(40, 44, 58))
            p.drawRect(dx, bar_y, dw, 15)
            p.setBrush(QColor(242, 182, 50))
            p.drawRect(dx, bar_y, int(dw * (pct / 100.0)), 15)
            
        if is_shorts:
            lb_x, lb_y = 40, 1100
            lb_w = 1000
        else:
            lb_x, lb_y = 1300, 150
            lb_w = 600
            
        f3 = QFont("Arial", 24, QFont.Bold)
        p.setFont(f3)
        p.setPen(QColor(242, 182, 50))
        p.drawText(lb_x, lb_y, "Leaderboard")
        
        order = sorted(e.nations, key=lambda n: (not n.alive, -n.tile_count, -n.troops))
        f4 = QFont("Arial", 20)
        p.setFont(f4)
        y_off = lb_y + 50
        for n in order[:8]:
            if n.alive:
                p.fillRect(lb_x, y_off - 20, 30, 30, QColor(*n.color))
                txt = f"{n.name} | {n.tile_count} tiles | ⚔{int(n.troops)} | 🏗{int(n.bp)}BP"
                p.setPen(QColor(220, 225, 234))
                p.drawText(lb_x + 50, y_off, txt)
                y_off += 30
                txt2 = f"     🏛 {n.cities}  |  🏭 {n.factories}  |  D:{n.defense_level}"
                p.setPen(QColor(170, 175, 190))
                p.drawText(lb_x + 50, y_off, txt2)
                y_off += 35
            else:
                p.fillRect(lb_x, y_off - 20, 30, 30, QColor(50, 50, 50))
                p.setPen(QColor(100, 100, 100))
                p.drawText(lb_x + 50, y_off, f"{n.name} (Eliminated)")
                y_off += 50
                
        p.end()
        
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.array(ptr, dtype=np.uint8).reshape((height, width, 4))
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        return arr

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 12, 18))
        e = self.engine
        if self._img is None:
            p.setPen(QColor(150, 155, 170))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Press  🌍 New Game  to generate a world")
            return
        w, h = float(self.width()), float(self.height())
        cols, rows = e.cols, e.rows
        s = min(w / cols, h / rows)
        dw, dh = cols * s, rows * s
        ox, oy = (w - dw) / 2.0, (h - dh) / 2.0
        self._geom = (s, ox, oy)
        p.drawImage(QRectF(ox, oy, dw, dh), self._img)

        if self.show_grid and s >= 4.0:
            p.setPen(QPen(QColor(0, 0, 0, 60), 1))
            for x in range(0, cols + 1, 8):
                p.drawLine(QPointF(ox + x * s, oy), QPointF(ox + x * s, oy + dh))
            for y in range(0, rows + 1, 8):
                p.drawLine(QPointF(ox, oy + y * s), QPointF(ox + dw, oy + y * s))

        # --- Draw City and Factory Markers ---
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Factories (Red Diamonds)
        p.setBrush(QColor(180, 60, 40, 220))
        p.setPen(QPen(QColor(255, 150, 100), 1))
        fac_size = max(2.0, s * 0.5)
        for x, y in e.factory_coords:
            cx = ox + (x + 0.5) * s
            cy = oy + (y + 0.5) * s
            path = QPainterPath()
            path.moveTo(cx, cy - fac_size/2)
            path.lineTo(cx + fac_size/2, cy)
            path.lineTo(cx, cy + fac_size/2)
            path.lineTo(cx - fac_size/2, cy)
            path.closeSubpath()
            p.drawPath(path)

        # Cities (Golden Circles)
        p.setBrush(QColor(255, 215, 0, 220))
        p.setPen(QPen(QColor(255, 255, 200), 1))
        city_size = max(3.0, s * 0.6)
        for x, y in e.city_coords:
            cx = ox + (x + 0.5) * s
            cy = oy + (y + 0.5) * s
            p.drawEllipse(QPointF(cx, cy), city_size/2, city_size/2)
            
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self.show_labels and s >= 3.5:
            f = QFont(self.font()); f.setBold(True)
            f.setPixelSize(int(max(9, min(18, s * 1.1))))
            p.setFont(f)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for n in e.nations:
                if not n.alive or n.tile_count == 0: continue
                cx = ox + (n.label_x + 0.5) * s
                cy = oy + (n.label_y + 0.5) * s
                text = f"{n.name} · {int(n.troops)}"
                path = QPainterPath()
                path.addText(QPointF(0, 0), f, text)
                br = path.boundingRect()
                path.translate(cx - br.width() / 2.0, cy - s * 1.8)
                
                # Better Text Outline Color (Deep rich black)
                p.setPen(QPen(QColor(15, 18, 25, 230), max(2.5, f.pixelSize() / 5.5)))
                # Better Text Fill Colors (Gold for selected, Soft Silver for others)
                if n.id == e.selected:
                    p.setBrush(QColor(242, 182, 50, 255)) # App's Gold theme
                else:
                    p.setBrush(QColor(230, 235, 245, 240)) # Soft silver-white
                    
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

    def _tile_at(self, pos):
        e = self.engine
        if e.terrain is None: return None
        s, ox, oy = self._geom
        x = int((pos.x() - ox) / s)
        y = int((pos.y() - oy) / s)
        if 0 <= x < e.cols and 0 <= y < e.rows: return x, y
        return None

    def mouseMoveEvent(self, ev):
        t = self._tile_at(ev.position())
        if t is None:
            self.hover_info.emit("")
            return
        x, y = t
        e = self.engine
        i = e._idx(x, y)
        biome = e.terrain[i]
        b_stats = BIOME_STATS[biome]
        
        if biome in WATER_BIOMES:
            txt = f"🌊 {b_stats['name']} ({x}, {y})"
        else:
            o = e.owner[i]
            if o == UNCLAIMED:
                base = f"🟫 Neutral {b_stats['name']}"
            else:
                n = e.nations[o]
                per_tile = n.troops / max(1, n.tile_count)
                base = (f"{n.name} — ⚔ {int(n.troops)} troops (~{per_tile:.1f}/tile) · "
                        f"{n.tile_count} tiles · 🏗 {int(n.bp)} BP")
                if n.mobilize_timer > 0: base += " · ⚡ Mobilized"
            if e.city[i]: base += " · 🏛 city"
            if e.factory[i]: base += " · 🏭 factory"
            txt = f"{base}   [Biome: {b_stats['name']} (Def x{b_stats['defense']:.1f}, Inc x{b_stats['income']:.1f})]   ({x}, {y})"
        self.hover_info.emit(txt)

    def mousePressEvent(self, ev):
        t = self._tile_at(ev.position())
        if t is None: return
        x, y = t
        e = self.engine
        o = e.owner[e._idx(x, y)]
        e.selected = None if (o == UNCLAIMED or o == e.selected) else o
        e.state_changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tile Wars · AI conquest & Biomes")
        self.resize(1300, 820)
        self._icons = {}
        self._current_cfg = None

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

        left = QVBoxLayout()
        self.canvas = MapCanvas(self.engine)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.hover_info.connect(lambda s: self.hover_lbl.setText(s))
        left.addWidget(self.canvas, 1)
        self.hover_lbl = QLabel("Hover the map for tile info · click a nation to track it")
        self.hover_lbl.setObjectName("HoverLabel")
        left.addWidget(self.hover_lbl)
        root.addLayout(left, 1)

        side_widget = QWidget()
        side_widget.setFixedWidth(340)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        root.addWidget(side_widget)

        title = QLabel("TILE WARS")
        title.setObjectName("TitleLabel")
        sub = QLabel("AI nations dynamically evaluate terrain, economy, and strategy")
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
        self.map_type_combo = QComboBox()
        self.map_type_combo.addItems(["Standard", "Transverse Oceans", "Extreme Biomes"])
        self.nations_spin = QSpinBox(); self.nations_spin.setRange(2, 12); self.nations_spin.setValue(8)
        form.addRow("Map size", self.size_combo)
        form.addRow("Map type", self.map_type_combo)
        form.addRow("Nations", self.nations_spin)
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
        self.restart_btn = QPushButton("🔄  Restart")
        self.restart_btn.clicked.connect(self.new_game)
        self.restart_btn.setEnabled(False)
        row.addWidget(self.play_btn)
        row.addWidget(self.step_btn)
        row.addWidget(self.restart_btn)
        pv.addLayout(row)
        
        self.export_btn = QPushButton("🎥  Export to YouTube / Shorts")
        self.export_btn.clicked.connect(self.export_video)
        if not VIDEO_EXPORT_ENABLED:
            self.export_btn.setEnabled(False)
            self.export_btn.setToolTip("Requires 'opencv-python' and 'numpy'. Run: pip install opencv-python numpy")
        pv.addWidget(self.export_btn)

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
        self.labels_chk = QCheckBox("Show nation labels (L)")
        self.labels_chk.setChecked(True)
        self.labels_chk.toggled.connect(self.toggle_labels)
        pv.addWidget(self.labels_chk)
        self.heatmap_chk = QCheckBox("Troop density heatmap (H)")
        self.heatmap_chk.toggled.connect(self.toggle_heatmap)
        pv.addWidget(self.heatmap_chk)
        self.grid_chk = QCheckBox("Show grid overlay (G)")
        self.grid_chk.toggled.connect(self.toggle_grid)
        pv.addWidget(self.grid_chk)
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

        QShortcut(QKeySequence("Space"), self, self.toggle_play)
        QShortcut(QKeySequence("N"), self, self.new_game)
        QShortcut(QKeySequence("S"), self, self.engine.tick)
        QShortcut(QKeySequence("L"), self, lambda: self.labels_chk.toggle())
        QShortcut(QKeySequence("H"), self, lambda: self.heatmap_chk.toggle())
        QShortcut(QKeySequence("G"), self, lambda: self.grid_chk.toggle())
        QShortcut(QKeySequence("Escape"), self, self.deselect)
        QShortcut(QKeySequence("R"), self, self.new_game)

        self.speed_changed(self.speed_slider.value())
        self.new_game()

    def _interval(self):
        v = self.speed_slider.value()
        return max(22, int(620 / v))

    def speed_changed(self, v):
        self.speed_lbl.setText(f"Speed ×{v}  ({self._interval()} ms / tick)")
        if self.timer.isActive():
            self.timer.setInterval(self._interval())

    def toggle_play(self):
        if self.engine.over: return
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("▶  Play")
        else:
            self.timer.start(self._interval())
            self.play_btn.setText("⏸  Pause")

    def toggle_labels(self, on):
        self.canvas.show_labels = on
        self.canvas.update()

    def toggle_heatmap(self, on):
        self.engine.heatmap = on
        self.canvas.update()

    def toggle_grid(self, on):
        self.canvas.show_grid = on
        self.canvas.update()

    def deselect(self):
        self.engine.selected = None
        self.engine.state_changed.emit()

    def new_game(self):
        cols, rows = MAP_SIZES[self.size_combo.currentText()]
        num_cities = max(5, (cols * rows) // 1000)
        cfg = GameConfig(cols=cols, rows=rows,
                         num_nations=self.nations_spin.value(),
                         num_cities=num_cities,
                         map_type=self.map_type_combo.currentText())
        self._current_cfg = cfg
        self.timer.stop()
        self.engine.new_game(cfg)
        self.log_box.clear()
        self.engine.log(f"🌍 New world: {cols}×{rows} · {cfg.num_nations} nations · "
                        f"{cfg.num_cities} cities · {self.engine.total_land} land tiles")
        self.timer.start(self._interval())
        self.play_btn.setText("⏸  Pause")
        self.play_btn.setEnabled(True)
        self.restart_btn.setEnabled(False)

    def export_video(self):
        if not VIDEO_EXPORT_ENABLED:
            QMessageBox.warning(self, "Export Disabled", "Video export requires 'opencv-python' and 'numpy'.\nPlease run: pip install opencv-python numpy")
            return
            
        formats = ["YouTube Video (1920x1080 16:9)", "YouTube Shorts (1080x1920 9:16)"]
        fmt, ok = QInputDialog.getItem(self, "Export Format", "Select video format:", formats, 0, False)
        if not ok: return
        
        filename, _ = QFileDialog.getSaveFileName(self, "Save Video", "tile_wars_export.mp4", "MP4 Files (*.mp4)")
        if not filename: return
        
        is_shorts = "Shorts" in fmt
        width, height = (1080, 1920) if is_shorts else (1920, 1080)
        
        self.timer.stop()
        self.engine.new_game(self._current_cfg)
        self.canvas.rebuild_image()
        
        progress = QProgressDialog("Rendering video... please wait.", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(filename, fourcc, 30.0, (width, height))
        
        max_ticks = 600
        for i in range(max_ticks):
            if progress.wasCanceled():
                break
            if self.engine.over:
                for _ in range(30):
                    frame = self.canvas.render_video_frame(width, height, is_shorts)
                    video.write(frame)
                break
            
            self.engine.tick()
            self.canvas.rebuild_image()
            frame = self.canvas.render_video_frame(width, height, is_shorts)
            video.write(frame)
            
            progress.setValue(int((i / max_ticks) * 100))
            QApplication.processEvents()
        
        video.release()
        progress.close()
        
        self.engine.new_game(self._current_cfg)
        self.timer.start(self._interval())
        
        QMessageBox.information(self, "Export Complete", f"Video saved successfully to:\n{filename}")

    def on_pick(self, item):
        nid = item.data(Qt.ItemDataRole.UserRole)
        self.engine.selected = None if self.engine.selected == nid else nid
        self.engine.state_changed.emit()

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
        if not e.nations: return
        order = sorted(e.nations, key=lambda n: (not n.alive, -n.tile_count, -n.troops))
        lst = self.leader_list
        lst.blockSignals(True)
        lst.clear()
        for n in order:
            if n.alive:
                mob = " ⚡" if n.mobilize_timer > 0 else ""
                text = (f"{n.name}  ·  {n.tile_count} tiles  ·  ⚔ {int(n.troops)}  ·  🏗 {int(n.bp)} BP\n"
                        f"     D:{n.defense_level}  ·  🏛 {n.cities}  ·  🏭 {n.factories}  ·  ☠{n.kills}{mob}")
            else:
                text = f"☠  {n.name} — eliminated (peak {n.peak_tiles} @ t{n.peak_tick})"
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
        if e.terrain is None: return
        owned = sum(n.tile_count for n in e.nations)
        pct = 100.0 * owned / max(1, e.total_land)
        leader = max(e.nations, key=lambda n: n.tile_count)
        alive_count = sum(1 for n in e.nations if n.alive)
        total_kills = sum(n.kills for n in e.nations)
        self.stats_lbl.setText(
            f"Tick {e.tick_n} · land claimed {pct:.1f}%\n"
            f"Leader: {leader.name} ({leader.tile_count} tiles, ⚔ {int(leader.troops)})\n"
            f"Alive: {alive_count}/{len(e.nations)} · total conquests: {total_kills}")

    def on_event(self, line):
        self.log_box.appendPlainText(line)

    def on_game_over(self, winner):
        self.timer.stop()
        self.play_btn.setText("🏁  Game over")
        self.play_btn.setEnabled(False)
        self.restart_btn.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Tile Wars")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()