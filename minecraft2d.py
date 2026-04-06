#!/usr/bin/env python3
"""
Mini Minecraft 2D
Controls:
  A / D or Arrow Keys  - Move left / right
  Space / W / Up       - Jump
  Left Mouse (hold)    - Mine block
  Right Mouse          - Place selected block
  1-5 or Scroll Wheel  - Select block
  Escape               - Quit
"""
import pygame
import sys
import math
import random

# ── Screen ────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1200, 700
FPS = 60
TILE = 40

# ── World ─────────────────────────────────────────────────────────────────────
WORLD_W = 240
WORLD_H = 64

# ── Block IDs ─────────────────────────────────────────────────────────────────
AIR     = 0
GRASS   = 1
DIRT    = 2
STONE   = 3
WOOD    = 4
LEAVES  = 5
SAND    = 6
BEDROCK = 7

# (face_color, top_color, hardness_seconds)
BLOCK_DATA = {
    GRASS:   ((119, 85,  57),  (107, 142, 35),  0.8),
    DIRT:    ((139, 100, 60),  (154, 115, 75),  0.6),
    STONE:   ((118, 118, 118), (138, 138, 138), 2.5),
    WOOD:    ((101, 76,  46),  (125, 98,  68),  1.5),
    LEAVES:  ((34,  100, 34),  (44,  120, 44),  0.3),
    SAND:    ((194, 178, 128), (212, 196, 148), 0.5),
    BEDROCK: ((40,  40,  40),  (55,  55,  55),  9999),
}

HOTBAR = [DIRT, STONE, WOOD, LEAVES, SAND]

GRAVITY    = 0.65
JUMP_VEL   = -14.5
MOVE_SPEED = 4.5
REACH      = 7   # blocks


# ── World generation ──────────────────────────────────────────────────────────

def make_world(seed=0):
    rng = random.Random(seed)
    world = [[AIR] * WORLD_W for _ in range(WORLD_H)]

    # Height map: layered sines + jitter
    raw = []
    for x in range(WORLD_W):
        h = (WORLD_H // 2
             + int(7  * math.sin(x * 0.09))
             + int(4  * math.sin(x * 0.21 + 1.3))
             + int(2  * math.sin(x * 0.44 + 0.7))
             + rng.randint(-1, 1))
        raw.append(max(8, min(WORLD_H - 12, h)))

    # 3-pass smooth
    for _ in range(3):
        s = []
        for x in range(WORLD_W):
            neighbours = raw[max(0, x-2): x+3]
            s.append(int(sum(neighbours) / len(neighbours)))
        raw = s
    heights = raw

    for x in range(WORLD_W):
        surf = heights[x]

        # Bedrock
        for y in range(WORLD_H - 3, WORLD_H):
            world[y][x] = BEDROCK

        # Stone
        for y in range(surf + 5, WORLD_H - 3):
            world[y][x] = STONE

        # Sand patch or normal dirt+grass
        if rng.random() < 0.08:
            for y in range(surf, surf + 5):
                if y < WORLD_H:
                    world[y][x] = SAND
        else:
            world[surf][x] = GRASS
            for y in range(surf + 1, surf + 5):
                if y < WORLD_H:
                    world[y][x] = DIRT

        # Trees
        if (rng.random() < 0.06
                and x > 4 and x < WORLD_W - 5
                and world[surf][x] == GRASS):
            th = rng.randint(4, 7)
            for ty in range(surf - th, surf):
                if 0 <= ty < WORLD_H:
                    world[ty][x] = WOOD
            for lx in range(x - 2, x + 3):
                for ly in range(surf - th - 2, surf - th + 2):
                    if 0 <= ly < WORLD_H and 0 <= lx < WORLD_W:
                        if world[ly][lx] == AIR:
                            world[ly][lx] = LEAVES

    return world, heights


# ── Camera ────────────────────────────────────────────────────────────────────

class Camera:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0

    def follow(self, tx, ty):
        self.x += (tx - SCREEN_W / 2 - self.x) * 0.12
        self.y += (ty - SCREEN_H / 2 - self.y) * 0.12

    def to_screen(self, wx, wy):
        return wx - self.x, wy - self.y

    def to_world(self, sx, sy):
        return sx + self.x, sy + self.y


# ── Particles ─────────────────────────────────────────────────────────────────

class Particle:
    def __init__(self, x, y, color):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(1, 4)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 2
        self.life = random.uniform(0.3, 0.7)
        self.color = color
        self.size = random.randint(3, 7)

    def update(self, dt):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.3
        self.life -= dt
        self.size = max(1, self.size - 0.05)

    def draw(self, surface, camera):
        sx, sy = camera.to_screen(self.x, self.y)
        alpha = max(0, min(255, int(self.life / 0.7 * 220)))
        s = pygame.Surface((int(self.size*2), int(self.size*2)), pygame.SRCALPHA)
        pygame.draw.rect(s, (*self.color, alpha), s.get_rect())
        surface.blit(s, (sx - self.size, sy - self.size))


# ── Player ────────────────────────────────────────────────────────────────────

class Player:
    W = int(TILE * 0.75)
    H = int(TILE * 1.85)

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.facing = 1   # 1=right, -1=left
        self.walk_frame = 0.0

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.W, self.H)

    def center(self):
        return self.x + self.W / 2, self.y + self.H / 2

    def update(self, world, keys):
        self.vx = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.vx = -MOVE_SPEED
            self.facing = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.vx = MOVE_SPEED
            self.facing = 1

        if self.on_ground and self.vx != 0:
            self.walk_frame += 0.15
        else:
            self.walk_frame = 0.0

        if (keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]) and self.on_ground:
            self.vy = JUMP_VEL
            self.on_ground = False

        self.vy = min(self.vy + GRAVITY, 22)

        self.x += self.vx
        self._resolve_x(world)
        self.y += self.vy
        self.on_ground = False
        self._resolve_y(world)

        self.x = max(0.0, min(WORLD_W * TILE - self.W, self.x))

    def _overlapping(self, world):
        r = self.rect()
        bx0, bx1 = r.left  // TILE, r.right  // TILE
        by0, by1 = r.top   // TILE, r.bottom // TILE
        hits = []
        for bx in range(bx0, bx1 + 1):
            for by in range(by0, by1 + 1):
                if 0 <= bx < WORLD_W and 0 <= by < WORLD_H and world[by][bx] != AIR:
                    hits.append(pygame.Rect(bx * TILE, by * TILE, TILE, TILE))
        return hits

    def _resolve_x(self, world):
        r = self.rect()
        for br in self._overlapping(world):
            if r.colliderect(br):
                if self.vx > 0:
                    self.x = br.left - self.W
                elif self.vx < 0:
                    self.x = br.right
                self.vx = 0
                r = self.rect()

    def _resolve_y(self, world):
        r = self.rect()
        for br in self._overlapping(world):
            if r.colliderect(br):
                if self.vy > 0:
                    self.y = br.top - self.H
                    self.on_ground = True
                elif self.vy < 0:
                    self.y = br.bottom
                self.vy = 0
                r = self.rect()

    def draw(self, surface, camera):
        sx, sy = camera.to_screen(self.x, self.y)
        sx, sy = int(sx), int(sy)
        f = self.facing

        # leg swing angle
        swing = math.sin(self.walk_frame) * 25 if self.on_ground else 15

        pw = self.W
        ph = self.H
        cx = sx + pw // 2

        head_h = int(ph * 0.30)
        body_h = int(ph * 0.38)
        leg_h  = int(ph * 0.32)
        leg_w  = int(pw * 0.36)

        # ── Legs ──
        for side, sign in (("L", -1), ("R", 1)):
            angle = swing * sign if self.vx != 0 else 0
            angle_r = math.radians(angle)
            lx = cx + sign * int(pw * 0.12) - leg_w // 2
            ly = sy + head_h + body_h
            # pivot from top of leg, draw rotated rect
            surf = pygame.Surface((leg_w, leg_h), pygame.SRCALPHA)
            pygame.draw.rect(surf, (50, 55, 120), (0, 0, leg_w, leg_h))
            pygame.draw.rect(surf, (35, 40, 100), (0, 0, leg_w, 4))
            rotated = pygame.transform.rotate(surf, -math.degrees(angle_r))
            ox = lx + leg_w // 2 - rotated.get_width() // 2
            oy = ly
            surface.blit(rotated, (ox, oy))

        # ── Body ──
        bx = sx + int(pw * 0.05)
        by = sy + head_h
        bw = int(pw * 0.90)
        pygame.draw.rect(surface, (65, 105, 185), (bx, by, bw, body_h))
        # shirt detail
        pygame.draw.rect(surface, (55, 90, 160), (bx, by + body_h // 3, bw, 3))
        pygame.draw.rect(surface, (80, 120, 200), (bx, by, bw, 5))

        # ── Head ──
        hx = sx + int(pw * 0.10)
        hy = sy
        hw = int(pw * 0.82)
        hh = head_h
        pygame.draw.rect(surface, (255, 213, 170), (hx, hy, hw, hh))   # skin
        # hair
        pygame.draw.rect(surface, (100, 65, 20), (hx, hy, hw, hh // 3))
        # eyes (face direction)
        ew = 6
        eh = 7
        eye_y = hy + hh // 2 - 2
        if f == 1:
            pygame.draw.rect(surface, (60, 60, 220), (hx + hw - 16, eye_y, ew, eh))
        else:
            pygame.draw.rect(surface, (60, 60, 220), (hx + 10, eye_y, ew, eh))
        # mouth
        pygame.draw.rect(surface, (180, 100, 80), (hx + hw//2 - 5, hy + hh - 6, 10, 3))


# ── Block drawing ─────────────────────────────────────────────────────────────

# Pre-build block surfaces for speed
_block_cache: dict = {}

def _make_block_surf(block_id):
    face, top, _ = BLOCK_DATA[block_id]
    s = pygame.Surface((TILE, TILE))
    s.fill(face)
    # top stripe
    pygame.draw.rect(s, top, (0, 0, TILE, TILE // 5))
    # subtle inner shadow on right/bottom
    shadow = tuple(max(0, c - 30) for c in face)
    pygame.draw.rect(s, shadow, (TILE - 3, 0, 3, TILE))
    pygame.draw.rect(s, shadow, (0, TILE - 3, TILE, 3))
    # border
    pygame.draw.rect(s, (0, 0, 0), s.get_rect(), 1)
    return s

def get_block_surf(block_id):
    if block_id not in _block_cache:
        _block_cache[block_id] = _make_block_surf(block_id)
    return _block_cache[block_id]


# Crack overlay surfaces (6 stages)
_crack_surfs: list = []

def _build_crack_surfs():
    for stage in range(6):
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        alpha = int(30 + stage * 35)
        s.fill((0, 0, 0, alpha))
        if stage == 0:
            _crack_surfs.append(s)
            continue
        col = (15, 8, 0, 200)
        cx, cy = TILE // 2, TILE // 2
        w = 2
        # radial cracks grow with stage
        lines = [
            ((cx, cy), (cx - 12, cy - 12)),
            ((cx, cy), (cx + 14, cy -  8)),
            ((cx, cy), (cx -  8, cy + 14)),
            ((cx, cy), (cx + 10, cy + 12)),
            ((cx - 12, cy - 12), (cx - 18, cy)),
            ((cx + 14, cy -  8), (TILE - 2, cy - 2)),
        ]
        for i, (p1, p2) in enumerate(lines[:stage + 1]):
            pygame.draw.line(s, col, p1, p2, w)
        _crack_surfs.append(s)

_build_crack_surfs()


def draw_block_at(surface, block_id, sx, sy, progress=0.0):
    surface.blit(get_block_surf(block_id), (sx, sy))
    if progress > 0:
        stage = min(5, int(progress * 6))
        surface.blit(_crack_surfs[stage], (sx, sy))


# ── Sky ───────────────────────────────────────────────────────────────────────

def make_sky():
    sky = pygame.Surface((SCREEN_W, SCREEN_H))
    top = (100, 175, 240)
    bot = (155, 215, 250)
    for y in range(SCREEN_H):
        t = y / SCREEN_H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        pygame.draw.line(sky, (r, g, b), (0, y), (SCREEN_W, y))
    # Sun
    pygame.draw.circle(sky, (255, 220, 55), (SCREEN_W - 80, 70), 38)
    pygame.draw.circle(sky, (255, 240, 120), (SCREEN_W - 80, 70), 28)
    # Clouds
    rng = random.Random(7)
    for _ in range(6):
        cx = rng.randint(50, SCREEN_W - 100)
        cy = rng.randint(30, 130)
        for dx, dy, r in [(-28, 0, 22), (0, -10, 28), (28, 0, 22), (14, 6, 18), (-14, 6, 18)]:
            pygame.draw.ellipse(sky, (240, 245, 255),
                                (cx + dx - r, cy + dy - r//2, r*2, r))
    return sky


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(surface, sel, font_sm, font_tiny):
    n = len(HOTBAR)
    slot_sz = 48
    gap = 4
    total_w = n * (slot_sz + gap) - gap
    ox = (SCREEN_W - total_w) // 2
    oy = SCREEN_H - slot_sz - 12

    for i, bid in enumerate(HOTBAR):
        x = ox + i * (slot_sz + gap)
        # background
        bg = (60, 60, 60) if i != sel else (200, 190, 50)
        pygame.draw.rect(surface, bg, (x - 2, oy - 2, slot_sz + 4, slot_sz + 4), border_radius=4)
        pygame.draw.rect(surface, (30, 30, 30), (x, oy, slot_sz, slot_sz), border_radius=3)

        # block preview (scaled)
        preview = pygame.transform.scale(get_block_surf(bid), (slot_sz - 8, slot_sz - 8))
        surface.blit(preview, (x + 4, oy + 4))

        # number
        num = font_tiny.render(str(i + 1), True, (200, 200, 200))
        surface.blit(num, (x + 3, oy + 3))

    # Controls legend (top-left)
    controls = [
        "A / D  — Move",
        "Space  — Jump",
        "LMB    — Mine",
        "RMB    — Place",
        "1-5    — Block",
    ]
    pad_surf = pygame.Surface((148, len(controls) * 20 + 10), pygame.SRCALPHA)
    pad_surf.fill((0, 0, 0, 100))
    surface.blit(pad_surf, (6, 6))
    for i, line in enumerate(controls):
        t = font_tiny.render(line, True, (220, 220, 220))
        surface.blit(t, (12, 10 + i * 20))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Mini Minecraft 2D")
    clock = pygame.time.Clock()

    font_sm   = pygame.font.SysFont("monospace", 22, bold=True)
    font_tiny = pygame.font.SysFont("monospace", 18)

    # Loading screen
    screen.fill((40, 40, 40))
    msg = font_sm.render("Generating world...", True, (220, 220, 220))
    screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2))
    pygame.display.flip()

    world, heights = make_world(seed=42)
    sky_surf = make_sky()

    # Spawn
    sx = WORLD_W // 2
    sy = heights[sx] - 2
    player  = Player(sx * TILE, sy * TILE)
    camera  = Camera()
    camera.x = player.x - SCREEN_W / 2
    camera.y = player.y - SCREEN_H / 2

    particles: list[Particle] = []

    # Mining state
    mine_block  = None   # (bx, by)
    mine_prog   = 0.0

    sel_idx = 0

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        # ── Events ────────────────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                for i, k in enumerate([pygame.K_1, pygame.K_2, pygame.K_3,
                                        pygame.K_4, pygame.K_5]):
                    if ev.key == k:
                        sel_idx = i
            elif ev.type == pygame.MOUSEWHEEL:
                sel_idx = (sel_idx - ev.y) % len(HOTBAR)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                # Place block
                mx, my = pygame.mouse.get_pos()
                wx, wy = camera.to_world(mx, my)
                bx, by = int(wx // TILE), int(wy // TILE)
                pcx, pcy = player.center()
                dist = math.hypot(bx - pcx / TILE, by - pcy / TILE)
                if (dist < REACH and 0 <= bx < WORLD_W and 0 <= by < WORLD_H
                        and world[by][bx] == AIR):
                    br = pygame.Rect(bx * TILE, by * TILE, TILE, TILE)
                    if not player.rect().colliderect(br):
                        world[by][bx] = HOTBAR[sel_idx]

        # ── Mining (hold LMB) ─────────────────────────────────────────────────
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            wx, wy = camera.to_world(mx, my)
            bx, by = int(wx // TILE), int(wy // TILE)
            pcx, pcy = player.center()
            dist = math.hypot(bx - pcx / TILE, by - pcy / TILE)

            if (0 <= bx < WORLD_W and 0 <= by < WORLD_H
                    and world[by][bx] != AIR and dist < REACH):
                if mine_block != (bx, by):
                    mine_block = (bx, by)
                    mine_prog  = 0.0
                else:
                    hardness = BLOCK_DATA[world[by][bx]][2]
                    mine_prog += dt / hardness
                    if mine_prog >= 1.0:
                        face_col = BLOCK_DATA[world[by][bx]][0]
                        cx_px = bx * TILE + TILE // 2
                        cy_px = by * TILE + TILE // 2
                        for _ in range(12):
                            particles.append(Particle(cx_px, cy_px, face_col))
                        world[by][bx] = AIR
                        mine_block = None
                        mine_prog  = 0.0
            else:
                mine_block = None
                mine_prog  = 0.0
        else:
            mine_block = None
            mine_prog  = 0.0

        # ── Update ────────────────────────────────────────────────────────────
        keys = pygame.key.get_pressed()
        player.update(world, keys)

        pcx, pcy = player.center()
        camera.follow(pcx, pcy)

        particles = [p for p in particles if p.life > 0]
        for p in particles:
            p.update(dt)

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.blit(sky_surf, (0, 0))

        # Visible block range
        cbx = int(camera.x // TILE) - 1
        cby = int(camera.y // TILE) - 1
        vw  = SCREEN_W // TILE + 3
        vh  = SCREEN_H // TILE + 3

        for by in range(cby, cby + vh):
            for bx in range(cbx, cbx + vw):
                if 0 <= bx < WORLD_W and 0 <= by < WORLD_H and world[by][bx] != AIR:
                    sx_, sy_ = camera.to_screen(bx * TILE, by * TILE)
                    prog = mine_prog if mine_block == (bx, by) else 0.0
                    draw_block_at(screen, world[by][bx], int(sx_), int(sy_), prog)

        # Highlight targeted block
        if pygame.mouse.get_pressed()[0] and mine_block:
            bx, by = mine_block
            tx, ty = camera.to_screen(bx * TILE, by * TILE)
            hl = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            hl.fill((255, 255, 255, 50))
            pygame.draw.rect(hl, (255, 255, 255, 180), hl.get_rect(), 2)
            screen.blit(hl, (int(tx), int(ty)))

        # Particles
        for p in particles:
            p.draw(screen, camera)

        # Player
        player.draw(screen, camera)

        # Crosshair at mouse
        mx, my = pygame.mouse.get_pos()
        pygame.draw.line(screen, (255, 255, 255), (mx - 10, my), (mx + 10, my), 2)
        pygame.draw.line(screen, (255, 255, 255), (mx, my - 10), (mx, my + 10), 2)
        pygame.draw.line(screen, (0, 0, 0), (mx - 10, my), (mx + 10, my), 1)
        pygame.draw.line(screen, (0, 0, 0), (mx, my - 10), (mx, my + 10), 1)

        # HUD
        draw_hud(screen, sel_idx, font_sm, font_tiny)

        # FPS
        fps_t = font_tiny.render(f"FPS {int(clock.get_fps())}", True, (255, 255, 255))
        screen.blit(fps_t, (SCREEN_W - fps_t.get_width() - 10, 10))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
