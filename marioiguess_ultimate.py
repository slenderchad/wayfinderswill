import pygame
import sys
import random
import os

# Try importing MySQL connector
try:
    import mysql.connector
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Initialize Pygame
pygame.init()
pygame.font.init()

SCREEN_WIDTH, SCREEN_HEIGHT = 1600, 900
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Wayfinder's Will")

clock = pygame.time.Clock()
font_title = pygame.font.SysFont("arial", 64, bold=True)
font_medium = pygame.font.SysFont("arial", 40, bold=True)
font_small = pygame.font.SysFont("arial", 28)

music = pygame.mixer.music.load(os.path.join(r"C:\Users\mohit\OneDrive\Desktop\PYTHON\marioiguess", "song.mp3"))
pygame.mixer.music.play(-1)
pygame.mixer.music.set_volume(0.5)

# --- ADVANCED RELATIONAL MySQL DATABASE SETUP ---
db_conn = None
db_cursor = None
if DB_AVAILABLE:
    try:
        db_conn = mysql.connector.connect(host="localhost", user="root", password="002409173200")
        db_cursor = db_conn.cursor()
        
        db_cursor.execute("CREATE DATABASE IF NOT EXISTS marioiguess_db;")
        db_cursor.execute("USE marioiguess_db;")
        
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                player_id INT AUTO_INCREMENT PRIMARY KEY,
                player_name VARCHAR(50) UNIQUE
            );
        """)
        
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                score_id INT AUTO_INCREMENT PRIMARY KEY,
                player_id INT,
                level_num INT,
                score INT,
                time_seconds INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
            );
        """)
        db_conn.commit()
    except Exception as e:
        print(f"MySQL Connection Error: {e}")
        DB_AVAILABLE = False

def save_score_mysql(name, lvl, scr, t):
    if DB_AVAILABLE and db_cursor and db_conn:
        try:
            db_cursor.execute("INSERT IGNORE INTO players (player_name) VALUES (%s)", (name,))
            db_conn.commit()
            
            db_cursor.execute("SELECT player_id FROM players WHERE player_name = %s", (name,))
            res = db_cursor.fetchone()
            if res:
                p_id = res[0]
                db_cursor.execute(
                    "INSERT INTO scores (player_id, level_num, score, time_seconds) VALUES (%s, %s, %s, %s)",
                    (p_id, lvl, scr, t)
                )
                db_conn.commit()
        except Exception as e:
            print(f"MySQL Insert Error: {e}")

# Level-wise leaderboard fetching function (Top 3 per level)
def fetch_level_leaderboard():
    if not DB_AVAILABLE or not db_cursor:
        return {}
    level_data = {}
    try:
        for lvl in range(1, 6):
            db_cursor.execute("""
                SELECT p.player_name, s.score, s.time_seconds 
                FROM scores s 
                INNER JOIN players p ON s.player_id = p.player_id 
                WHERE s.level_num = %s 
                ORDER BY s.time_seconds ASC LIMIT 3;
            """, (lvl,))
            level_data[lvl] = db_cursor.fetchall()
    except Exception:
        pass
    return level_data

# --- GAME STATES & CONFIG ---
game_state = "TITLE"  
selected_menu = 0  
selected_level = 0    
current_level = 1

player_name = "Hero"
input_name = "Hero"

score = 0
target_coin_count = 10
final_time = 0
start_ticks = 0

# Player Setup
player = pygame.Rect(50, 400, 25, 40)
vel_y = 0
is_grounded = False
is_dragging = False
offset_x = offset_y = 0
has_gun = False

bullets = []
boss_bullets = []

# Level Elements
finish_flag = pygame.Rect(1460, 680, 80, 140)
platforms = []
hazards = []
lasers = []
coins = []
aliens = []
boss = None
gun_pickup = None
level5_phase = "COINS"

# --- LOAD ASSETS ---
def load_image_safe(filename, width, height, fallback_color):
    try:
        img = pygame.image.load(filename).convert_alpha()
        return pygame.transform.smoothscale(img, (width, height))
    except Exception:
        surf = pygame.Surface((width, height))
        surf.fill(fallback_color)
        return surf

ASSET_DIR = r"C:\Users\mohit\OneDrive\Desktop\PYTHON\marioiguess"

player_image = load_image_safe(os.path.join(ASSET_DIR, "mainguy.png"), player.width, player.height, (46, 204, 113))
sky_image = load_image_safe(os.path.join(ASSET_DIR, "sky.jpg"), SCREEN_WIDTH, SCREEN_HEIGHT, (41, 128, 185))
grass_image = load_image_safe(os.path.join(ASSET_DIR, "grass.jpg"), SCREEN_WIDTH, 100, (39, 174, 96))
hazard_template = load_image_safe(os.path.join(ASSET_DIR, "hazard.jpg"), 40, 40, (231, 76, 60))
coin_image = load_image_safe(os.path.join(ASSET_DIR, "coin.png"), 30, 30, (241, 196, 15))
flag_image = load_image_safe(os.path.join(ASSET_DIR, "flag.png"), 80, 140, (255, 255, 255))
alien_image = load_image_safe(os.path.join(ASSET_DIR, "alien.png"), 25, 25, (155, 89, 182))
gun_image = load_image_safe(os.path.join(ASSET_DIR, "gun.png"), 35, 20, (127, 140, 141))
boss_image = load_image_safe(os.path.join(ASSET_DIR, "boss.png"), 80, 120, (142, 68, 173))
title_image = load_image_safe(os.path.join(ASSET_DIR, "title.png"), 1600, 900, (241, 196, 15))

def draw_tiled_hazard(surface, img, rect):
    img_w, img_h = img.get_size()
    if img_w == 0 or img_h == 0: return
    for x in range(rect.x, rect.x + rect.width, img_w):
        for y in range(rect.y, rect.y + rect.height, img_h):
            dw = min(img_w, rect.x + rect.width - x)
            dh = min(img_h, rect.y + rect.height - y)
            surface.blit(img.subsurface((0, 0, dw, dh)), (x, y))

def load_level(lvl):
    global hazards, lasers, coins, aliens, boss, finish_flag, start_ticks, score, vel_y, platforms, has_gun, gun_pickup, bullets, boss_bullets, target_coin_count, level5_phase
    score = 0
    vel_y = 0
    start_ticks = pygame.time.get_ticks()
    player.x = 50
    player.y = 400
    has_gun = False
    hazards.clear()
    lasers.clear()
    coins.clear()
    aliens.clear()
    platforms.clear()
    bullets.clear()
    boss_bullets.clear()
    boss = None
    gun_pickup = None
    level5_phase = "COINS"

    hazards.append(pygame.Rect(0, 0, SCREEN_WIDTH, 40))
    platforms.append(pygame.Rect(0, 820, SCREEN_WIDTH, 100))

    if lvl == 1:
        target_coin_count = 10
        hazards.append(pygame.Rect(500, 720, 500, 100))
        finish_flag = pygame.Rect(1460, 680, 80, 140)

    elif lvl == 2:
        target_coin_count = 12
        platforms.append(pygame.Rect(350, 650, 300, 30))
        platforms.append(pygame.Rect(800, 500, 300, 30))
        hazards.append(pygame.Rect(400, 720, 700, 100))
        finish_flag = pygame.Rect(1460, 680, 80, 140)
        for _ in range(4):
            aliens.append({"pos": pygame.math.Vector2(random.randint(500, 1300), random.randint(200, 600)), "rect": pygame.Rect(0,0,25,25)})

    elif lvl == 3:
        target_coin_count = 15
        platforms.append(pygame.Rect(300, 600, 200, 30))
        platforms.append(pygame.Rect(700, 450, 200, 30))
        platforms.append(pygame.Rect(1100, 600, 200, 30))
        hazards.append(pygame.Rect(200, 720, 1000, 100))
        lasers.append({"rect": pygame.Rect(500, 350, 300, 15), "dir": 2, "min_x": 400, "max_x": 1000})
        finish_flag = pygame.Rect(1460, 680, 80, 140)
        for _ in range(6):
            aliens.append({"pos": pygame.math.Vector2(random.randint(400, 1400), random.randint(150, 650)), "rect": pygame.Rect(0,0,25,25)})

    elif lvl == 4:
        target_coin_count = 10
        gun_pickup = pygame.Rect(750, 550, 35, 20)
        hazards.append(pygame.Rect(450, 720, 600, 100))
        finish_flag = pygame.Rect(1460, 680, 80, 140)
        for _ in range(8):
            aliens.append({"pos": pygame.math.Vector2(random.randint(600, 1400), random.randint(200, 600)), "rect": pygame.Rect(0,0,25,25)})

    elif lvl == 5:
        target_coin_count = 8
        has_gun = True
        hazards.append(pygame.Rect(300, 720, 900, 100))
        finish_flag = pygame.Rect(1460, 680, 80, 140)

    while len(coins) < target_coin_count:
        cx, cy = random.randint(100, SCREEN_WIDTH - 100), random.randint(150, 750)
        c_rect = pygame.Rect(cx, cy, 30, 30)
        if not any(c_rect.colliderect(h) for h in hazards):
            coins.append(c_rect)

# --- MAIN GAME LOOP ---
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            if DB_AVAILABLE and db_conn: db_conn.close()
            pygame.quit()
            sys.exit()

        if game_state == "TITLE":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DOWN: selected_menu = (selected_menu + 1) % 3
                elif event.key == pygame.K_UP: selected_menu = (selected_menu - 1) % 3
                elif event.key == pygame.K_RETURN:
                    if selected_menu == 0: game_state = "NAME_INPUT"
                    elif selected_menu == 1: game_state = "LEADERBOARD"
                    elif selected_menu == 2: pygame.quit(); sys.exit()

        elif game_state == "NAME_INPUT":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    player_name = input_name.strip() if input_name.strip() else "Hero"
                    game_state = "LEVEL_SELECT"
                elif event.key == pygame.K_BACKSPACE:
                    input_name = input_name[:-1]
                else:
                    if event.unicode.isalnum() or event.unicode.isspace() or event.unicode in "_-":
                        input_name += event.unicode

        elif game_state == "LEVEL_SELECT":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DOWN: selected_level = (selected_level + 1) % 5
                elif event.key == pygame.K_UP: selected_level = (selected_level - 1) % 5
                elif event.key == pygame.K_RETURN:
                    current_level = selected_level + 1
                    load_level(current_level)
                    game_state = "PLAYING"
                elif event.key == pygame.K_BACKSPACE: game_state = "TITLE"

        elif game_state == "LEADERBOARD":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE: game_state = "TITLE"
                elif event.key == pygame.K_a: game_state = "ANALYTICS"  # Press A for MySQL JOIN & AGGREGATE

        elif game_state == "ANALYTICS":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                game_state = "LEADERBOARD"

        elif game_state == "PLAYING":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r: load_level(current_level)
                elif event.key == pygame.K_m: game_state = "TITLE"
                elif event.key == pygame.K_SPACE and has_gun:
                    bullets.append({"rect": pygame.Rect(player.centerx, player.centery, 12, 6), "dir": 1})
            
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if player.collidepoint(event.pos):
                    is_dragging = True
                    offset_x = player.x - event.pos[0]
                    offset_y = player.y - event.pos[1]
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                is_dragging = False
            elif event.type == pygame.MOUSEMOTION and is_dragging:
                player.x = event.pos[0] + offset_x
                player.y = event.pos[1] + offset_y

        elif game_state == "WIN":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    load_level(current_level)
                    game_state = "PLAYING"
                elif event.key == pygame.K_m:
                    game_state = "TITLE"
                elif event.key == pygame.K_n:  
                    if current_level < 5:
                        current_level += 1
                        load_level(current_level)
                        game_state = "PLAYING"
                    else:
                        game_state = "CREDITS"

        elif game_state == "CREDITS":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                game_state = "TITLE"

    # ================= GAME UPDATE LOGIC =================
    if game_state == "PLAYING":
        vel_y += 0.1
        player.y += vel_y

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a] or keys[pygame.K_KP_4]: player.x -= 8
        if keys[pygame.K_RIGHT] or keys[pygame.K_d] or keys[pygame.K_KP_6]: player.x += 8
        if keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_KP_8]: 
            vel_y = -5
            is_grounded = False
        if keys[pygame.K_DOWN] or keys[pygame.K_s] or keys[pygame.K_KP_2]: 
            vel_y = 10
            is_grounded = False

        if player.left > SCREEN_WIDTH: player.left = 0
        elif player.right < 0: player.right = SCREEN_WIDTH

        is_grounded = False
        for p in platforms:
            if player.colliderect(p) and vel_y > 0:
                player.bottom = p.top
                vel_y = 0
                is_grounded = True

        for h in hazards:
            if player.colliderect(h): load_level(current_level)

        for l in lasers:
            l["rect"].x += l["dir"] * 3
            if l["rect"].x < l["min_x"] or l["rect"].x > l["max_x"]:
                l["dir"] *= -1
            if player.colliderect(l["rect"]): load_level(current_level)

        if gun_pickup and player.colliderect(gun_pickup):
            has_gun = True
            gun_pickup = None

        for b in bullets[:]:
            b["rect"].x += 16 * b["dir"]
            if b["rect"].x > SCREEN_WIDTH or b["rect"].x < 0:
                bullets.remove(b)
                continue
            hit_alien = None
            for alien in aliens:
                if b["rect"].colliderect(alien["rect"]):
                    hit_alien = alien
                    break
            if hit_alien:
                aliens.remove(hit_alien)
                if b in bullets: bullets.remove(b)
                continue
            if boss and b["rect"].colliderect(boss["rect"]):
                boss["health"] -= 1
                if b in bullets: bullets.remove(b)
                if boss["health"] <= 0: boss = None
                continue

        task_completed = False
        if current_level in [1, 2, 3]:
            if len(coins) == 0: task_completed = True
        elif current_level == 4:
            if len(coins) == 0 and len(aliens) == 0: task_completed = True
        elif current_level == 5:
            if level5_phase == "COINS" and len(coins) == 0:
                level5_phase = "ALIENS"
                for _ in range(8):
                    aliens.append({"pos": pygame.math.Vector2(random.randint(200, 1400), random.randint(200, 600)), "rect": pygame.Rect(0,0,25,25)})
            elif level5_phase == "ALIENS" and len(aliens) == 0:
                level5_phase = "BOSS"
                boss = {"rect": pygame.Rect(1200, 650, 80, 120), "health": 12, "max_health": 12, "dir": -1.5}
            if level5_phase == "BOSS" and boss is None:
                task_completed = True

        for alien in aliens:
            dir_vec = pygame.math.Vector2(player.center) - alien["pos"]
            if dir_vec.length() > 0:
                dir_vec = dir_vec.normalize() * 1.0  
                alien["pos"] += dir_vec
                alien["rect"].center = (int(alien["pos"].x), int(alien["pos"].y))
            if player.colliderect(alien["rect"]): load_level(current_level)

        if boss:
            boss["rect"].x += boss["dir"]
            if boss["rect"].left < 800 or boss["rect"].right > SCREEN_WIDTH - 50:
                boss["dir"] *= -1
            if player.colliderect(boss["rect"]): load_level(current_level)

            if random.randint(1, 50) == 1:
                boss_bullets.append(pygame.Rect(boss["rect"].left, boss["rect"].centery, 18, 8))

        for bb in boss_bullets[:]:
            bb.x -= 8
            if bb.right < 0:
                boss_bullets.remove(bb)
            elif player.colliderect(bb):
                load_level(current_level)

        for coin in coins[:]:
            if player.colliderect(coin):
                coins.remove(coin)
                score += 1

        if task_completed and player.colliderect(finish_flag):
            final_time = (pygame.time.get_ticks() - start_ticks) // 1000
            game_state = "WIN"
            save_score_mysql(player_name, current_level, score, final_time)

    # ================= DRAWING SECTION =================
    screen.blit(sky_image, (0, 0))
    screen.blit(grass_image, (0, 820))

    for p in platforms[1:]:
        pygame.draw.rect(screen, (46, 204, 113), p)

    if game_state == "TITLE":
        screen.fill((15, 20, 30))
        screen.blit(title_image, (0, 0))

        opts = ["Start Game", "Leaderboard", "Exit"]
        for idx, text in enumerate(opts):
            color = (241, 196, 15) if idx == selected_menu else (189, 195, 199)
            rendered = font_medium.render(text, True, color)
            screen.blit(rendered, (SCREEN_WIDTH // 2 - rendered.get_width() // 2, 450 + (idx * 75)))

    elif game_state == "NAME_INPUT":
        screen.fill((15, 20, 30))
        t1 = font_title.render("ENTER YOUR NAME", True, (241, 196, 15))
        box_surf = font_medium.render(f"[ {input_name}_ ]", True, (255, 255, 255))
        t2 = font_small.render("Type your name and press [ENTER] to continue", True, (127, 140, 141))

        screen.blit(t1, (SCREEN_WIDTH // 2 - t1.get_width() // 2, 250))
        screen.blit(box_surf, (SCREEN_WIDTH // 2 - box_surf.get_width() // 2, 380))
        screen.blit(t2, (SCREEN_WIDTH // 2 - t2.get_width() // 2, 500))

    elif game_state == "LEVEL_SELECT":
        screen.fill((15, 20, 30))
        title = font_title.render(f"WELCOME, {player_name.upper()}!", True, (241, 196, 15))
        sub_t = font_small.render("SELECT LEVEL", True, (127, 140, 141))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 100))
        screen.blit(sub_t, (SCREEN_WIDTH // 2 - sub_t.get_width() // 2, 170))
        
        lvls = [
            "Level 1: GET IT",
            "Level 2: OH NO ALIEN",
            "Level 3: LASER HAWWW",
            "Level 4: PEW PEW IT",
            "Level 5: IT'S JABBA"
        ]
        for idx, desc in enumerate(lvls):
            color = (241, 196, 15) if idx == selected_level else (189, 195, 199)
            rendered = font_medium.render(desc, True, color)
            screen.blit(rendered, (SCREEN_WIDTH // 2 - rendered.get_width() // 2, 270 + (idx * 70)))

        hint = font_small.render("Press [ENTER] to Launch Level | [BACKSPACE] to Back", True, (127, 140, 141))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 680))

    elif game_state == "LEADERBOARD":
        screen.fill((15, 20, 30))
        title = font_title.render("LEVEL-WISE LEADERBOARD", True, (241, 196, 15))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 30))

        level_records = fetch_level_leaderboard()
        y_pos = 110
        for lvl in range(1, 6):
            lvl_header = font_small.render(f"--- Level {lvl} ---", True, (52, 152, 219))
            screen.blit(lvl_header, (SCREEN_WIDTH // 2 - lvl_header.get_width() // 2, y_pos))
            y_pos += 30
            
            records = level_records.get(lvl, [])
            if records:
                for i, r in enumerate(records):
                    text = font_small.render(f"{i+1}. {r[0]} | Score: {r[1]} | Time: {r[2]}s", True, (236, 240, 241))
                    screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, y_pos))
                    y_pos += 28
            else:
                no_rec = font_small.render("No records yet.", True, (127, 140, 141))
                screen.blit(no_rec, (SCREEN_WIDTH // 2 - no_rec.get_width() // 2, y_pos))
                y_pos += 28
            y_pos += 5

        hint = font_small.render("Press [A] for MySQL Analytics (JOIN & AVG) | [BACKSPACE] to Return", True, (127, 140, 141))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 850))

    elif game_state == "ANALYTICS":
        screen.fill((15, 20, 30))
        title = font_title.render("MYSQL DBMS ANALYTICS (JOIN & AGGREGATES)", True, (241, 196, 15))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 60))

        join_rows = []
        group_rows = []
        if DB_AVAILABLE and db_cursor:
            try:
                db_cursor.execute("""
                    SELECT p.player_name, s.level_num, s.score, s.time_seconds 
                    FROM scores s 
                    INNER JOIN players p ON s.player_id = p.player_id 
                    ORDER BY s.time_seconds ASC LIMIT 3;
                """)
                join_rows = db_cursor.fetchall()

                db_cursor.execute("""
                    SELECT level_num, AVG(time_seconds), MAX(score) 
                    FROM scores 
                    GROUP BY level_num;
                """)
                group_rows = db_cursor.fetchall()
            except Exception:
                pass

        h1 = font_small.render("--- MySQL INNER JOIN: Top Player Records ---", True, (46, 204, 113))
        screen.blit(h1, (SCREEN_WIDTH // 2 - h1.get_width() // 2, 150))
        y_off = 190
        if join_rows:
            for r in join_rows:
                txt = font_small.render(f"Player: {r[0]} | Level: {r[1]} | Score: {r[2]} | Time: {r[3]}s", True, (255, 255, 255))
                screen.blit(txt, (SCREEN_WIDTH // 2 - txt.get_width() // 2, y_off))
                y_off += 40
        else:
            no_j = font_small.render("No MySQL records found yet.", True, (200, 100, 100))
            screen.blit(no_j, (SCREEN_WIDTH // 2 - no_j.get_width() // 2, y_off))

        h2 = font_small.render("--- MySQL GROUP BY & AVG: Level Statistics ---", True, (52, 152, 219))
        screen.blit(h2, (SCREEN_WIDTH // 2 - h2.get_width() // 2, 360))
        y_off2 = 410
        if group_rows:
            for r in group_rows:
                avg_t = round(r[1], 1)
                txt2 = font_small.render(f"Level {r[0]} | Avg Time: {avg_t}s | Max Score: {r[2]}", True, (255, 255, 255))
                screen.blit(txt2, (SCREEN_WIDTH // 2 - txt2.get_width() // 2, y_off2))
                y_off2 += 40
        else:
            no_g = font_small.render("No group data available yet.", True, (200, 100, 100))
            screen.blit(no_g, (SCREEN_WIDTH // 2 - no_g.get_width() // 2, y_off2))

        back = font_small.render("Press [BACKSPACE] to return to Leaderboard", True, (127, 140, 141))
        screen.blit(back, (SCREEN_WIDTH // 2 - back.get_width() // 2, 680))

    elif game_state == "CREDITS":
        screen.fill((10, 10, 15))
        c_title = font_title.render("GAME CREDITS & STATS TABLE", True, (241, 196, 15))
        screen.blit(c_title, (SCREEN_WIDTH // 2 - c_title.get_width() // 2, 80))

        rows = []
        if DB_AVAILABLE and db_cursor:
            try:
                db_cursor.execute("""
                    SELECT p.player_name, s.level_num, s.score, s.time_seconds 
                    FROM scores s 
                    INNER JOIN players p ON s.player_id = p.player_id 
                    ORDER BY s.timestamp DESC LIMIT 5;
                """)
                rows = db_cursor.fetchall()
            except Exception:
                pass

        header = font_small.render("PLAYER     |     LEVEL     |     SCORE     |     TIME", True, (127, 140, 141))
        screen.blit(header, (SCREEN_WIDTH // 2 - header.get_width() // 2, 190))
        pygame.draw.line(screen, (100, 100, 100), (SCREEN_WIDTH // 2 - 300, 230), (SCREEN_WIDTH // 2 + 300, 230), 2)

        if rows:
            for i, row in enumerate(rows):
                r_text = font_small.render(f"  {row[0]}      |        Level {row[1]}      |        {row[2]}        |     {row[3]}s", True, (255, 255, 255))
                screen.blit(r_text, (SCREEN_WIDTH // 2 - r_text.get_width() // 2, 260 + (i * 50)))

        credit_text = font_medium.render("~an fml. prod.", True, (231, 76, 60))
        screen.blit(credit_text, (SCREEN_WIDTH // 2 - credit_text.get_width() // 2, 620))

        back_hint = font_small.render("Press [BACKSPACE] to Return to Title Menu", True, (150, 150, 150))
        screen.blit(back_hint, (SCREEN_WIDTH // 2 - back_hint.get_width() // 2, 720))

    elif game_state in ["PLAYING", "WIN"]:
        for h in hazards:
            draw_tiled_hazard(screen, hazard_template, h)

        for l in lasers:
            pygame.draw.rect(screen, (231, 76, 60), l["rect"])

        if gun_pickup:
            # Highlight ring / glowing yellow box around gun pickup so it's prominent
            pygame.draw.rect(screen, (241, 196, 15), gun_pickup.inflate(8, 8), 3, border_radius=4)
            screen.blit(gun_image, gun_pickup)

        for b in bullets:
            pygame.draw.rect(screen, (241, 196, 15), b["rect"])

        for bb in boss_bullets:
            pygame.draw.rect(screen, (231, 76, 60), bb)

        for alien in aliens:
            screen.blit(alien_image, alien["rect"])

        if boss:
            screen.blit(boss_image, boss["rect"])
            pygame.draw.rect(screen, (192, 57, 43), (boss["rect"].x, boss["rect"].y - 15, 80, 10))
            pygame.draw.rect(screen, (46, 204, 113), (boss["rect"].x, boss["rect"].y - 15, 80 * (boss["health"] / boss["max_health"]), 10))

        for coin in coins: screen.blit(coin_image, coin)
        
        task_ready = (current_level in [1, 2, 3] and len(coins) == 0) or \
                     (current_level == 4 and len(coins) == 0 and len(aliens) == 0) or \
                     (current_level == 5 and level5_phase == "BOSS" and boss is None)
        
        if task_ready:
            screen.blit(flag_image, finish_flag)

        screen.blit(player_image, player)

        if has_gun:
            screen.blit(gun_image, (player.right - 8, player.centery - 2))

        seconds = final_time if game_state == "WIN" else (pygame.time.get_ticks() - start_ticks) // 1000
        
        status = f"Lvl {current_level}" + (f" [{level5_phase}]" if current_level == 5 else "")
        task_status = "READY!" if task_ready else "Complete Coins!"
        
        hud_text = font_small.render(f"{status} | Coins: {score}/{target_coin_count} | Flag: {task_status} | [M] Menu", True, (255, 255, 255))
        timer_text = font_small.render(f"Time: {seconds}s", True, (255, 255, 255))
        
        # Centered player name with custom color tuple (241, 196, 15)
        name_center_text = font_medium.render(f"{player_name}", True, (255, 255, 255))
        
        screen.blit(hud_text, (15, 15))
        screen.blit(name_center_text, (SCREEN_WIDTH // 2 - name_center_text.get_width() // 2, 12))
        screen.blit(timer_text, (SCREEN_WIDTH - timer_text.get_width() - 30, 15))

        if game_state == "WIN":
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(220)
            overlay.fill((10, 10, 15))
            screen.blit(overlay, (0, 0))

            win_title = font_title.render("VICTORY!", True, (241, 196, 15))
            win_msg = font_medium.render(f"Great Job, {player_name}! Score: {score} | Time: {seconds}s", True, (236, 240, 241))
            win_hint = font_small.render("Press 'N' for Next Level | 'R' to Replay | 'M' for Menu", True, (127, 140, 141))
            
            screen.blit(win_title, (SCREEN_WIDTH // 2 - win_title.get_width() // 2, 300))
            screen.blit(win_msg, (SCREEN_WIDTH // 2 - win_msg.get_width() // 2, 420))
            screen.blit(win_hint, (SCREEN_WIDTH // 2 - win_hint.get_width() // 2, 510))

    pygame.display.flip()
    clock.tick(60)