"""
Zombie Survival — всё в одном файле.
Flask-сервер + HTML + CSS + JS (Three.js) в одном main.py.
Этап 1: меню, режим зомби-выживания, пистолет, нож, улучшенная графика.
Исправлено: движение (фокус на canvas, preventDefault для WASD).
Запуск: python main.py
"""
from flask import Flask, jsonify, request, Response
import os
import json
import time
import logging
from functools import wraps
from threading import Lock

# ============ КОНФИГ ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_FILE = os.path.join(BASE_DIR, 'scores.json')
MAX_SCORES = 100
TOP_N = 10
MAX_NAME_LEN = 20
RATE_LIMIT_SECONDS = 2
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('zombie-server')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

file_lock = Lock()
last_post_by_ip = {}

def rate_limited(ip):
    now = time.time()
    last = last_post_by_ip.get(ip, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return True
    last_post_by_ip[ip] = now
    return False

def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.warning(f'Не удалось прочитать {path}: {e}')
        return default

def _save_json(path, data):
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log.error(f'Не удалось сохранить {path}: {e}')
        return False

def load_scores(): return _load_json(SCORES_FILE, [])
def save_scores(s): return _save_json(SCORES_FILE, s)

def json_endpoint(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            r = fn(*a, **kw)
            if isinstance(r, tuple): return r
            return jsonify(r)
        except Exception as e:
            log.exception(f'Ошибка в {fn.__name__}: {e}')
            return jsonify({'error': 'internal_error', 'message': str(e)}), 500
    return wrapper

def require_json(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not request.is_json:
            return jsonify({'error': 'json_required'}), 400
        return fn(*a, **kw)
    return wrapper

# ============ HTML / CSS / JS ============

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zombie Survival</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  overflow: hidden; background: #000;
  font-family: 'Courier New', monospace; color: #fff;
  user-select: none;
}
canvas { display: block; }

#menu {
  position: absolute; inset: 0; z-index: 100;
  background: linear-gradient(135deg, #1a0000 0%, #000 100%);
  display: flex; flex-direction: column;
  justify-content: center; align-items: center;
}
#menu h1 {
  font-size: 72px; color: #c00; letter-spacing: 4px;
  text-shadow: 0 0 30px #f00, 0 0 60px #900;
  margin-bottom: 10px;
}
#menu .subtitle {
  color: #888; font-size: 18px; margin-bottom: 50px; letter-spacing: 2px;
}
#menu button {
  width: 320px; padding: 18px; margin: 10px;
  font-size: 22px; font-family: inherit; font-weight: bold;
  background: transparent; color: #fff;
  border: 2px solid #c00; border-radius: 4px;
  cursor: pointer; transition: all 0.2s;
  letter-spacing: 2px;
}
#menu button:hover {
  background: #c00; color: #000; box-shadow: 0 0 20px #f00;
}
#menu button:disabled {
  opacity: 0.3; cursor: not-allowed; border-color: #555;
}
#menu button:disabled:hover { background: transparent; color: #fff; box-shadow: none; }

#hud {
  position: absolute; inset: 0; pointer-events: none;
  display: none; z-index: 10;
}
#hud.active { display: block; }
#hp-bar {
  position: absolute; bottom: 30px; left: 30px;
  width: 280px; height: 28px;
  background: rgba(0,0,0,0.6); border: 2px solid #900;
  border-radius: 4px; overflow: hidden;
}
#hp-fill {
  height: 100%; background: linear-gradient(90deg, #f00, #f80);
  width: 100%; transition: width 0.15s;
}
#hp-text {
  position: absolute; bottom: 32px; left: 36px;
  font-size: 18px; font-weight: bold; text-shadow: 1px 1px 2px #000;
}
#ammo {
  position: absolute; bottom: 30px; right: 30px;
  text-align: right; text-shadow: 1px 1px 3px #000;
}
#ammo .weapon { font-size: 18px; color: #fa0; letter-spacing: 2px; }
#ammo .count { font-size: 48px; color: #fff; font-weight: bold; }
#ammo .count.low { color: #f00; }
#ammo .reloading { color: #fa0; font-size: 18px; }
#score-box {
  position: absolute; top: 30px; left: 30px;
  font-size: 20px; text-shadow: 1px 1px 3px #000;
}
#score-box .wave { color: #f80; font-size: 28px; font-weight: bold; }
#score-box .score { color: #fff; }
#crosshair {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 24px; height: 24px;
}
#crosshair::before, #crosshair::after {
  content: ''; position: absolute; background: rgba(255,255,255,0.8);
}
#crosshair::before { width: 2px; height: 24px; left: 11px; top: 0; }
#crosshair::after { width: 24px; height: 2px; left: 0; top: 11px; }
#damage-overlay {
  position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle, transparent 30%, rgba(200,0,0,0.7) 100%);
  opacity: 0; transition: opacity 0.15s;
}
#damage-overlay.hit { opacity: 1; }
#hit-marker {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 40px; height: 40px; opacity: 0;
}
#hit-marker::before, #hit-marker::after {
  content: ''; position: absolute; background: #f00; transform-origin: center;
}
#hit-marker::before { width: 2px; height: 40px; left: 19px; top: 0; transform: rotate(45deg); }
#hit-marker::after { width: 2px; height: 40px; left: 19px; top: 0; transform: rotate(-45deg); }

#pause {
  position: absolute; inset: 0; z-index: 50;
  background: rgba(0,0,0,0.85);
  display: none; flex-direction: column;
  justify-content: center; align-items: center;
}
#pause.active { display: flex; }
#pause h2 { font-size: 56px; color: #c00; margin-bottom: 40px; letter-spacing: 4px; }
#pause button {
  width: 280px; padding: 16px; margin: 8px;
  font-size: 20px; font-family: inherit; font-weight: bold;
  background: transparent; color: #fff;
  border: 2px solid #c00; border-radius: 4px;
  cursor: pointer; transition: all 0.2s; letter-spacing: 2px;
}
#pause button:hover { background: #c00; color: #000; }

#gameover {
  position: absolute; inset: 0; z-index: 60;
  background: rgba(0,0,0,0.92);
  display: none; flex-direction: column;
  justify-content: center; align-items: center;
}
#gameover.active { display: flex; }
#gameover h1 { font-size: 72px; color: #c00; margin-bottom: 20px; letter-spacing: 4px; }
#gameover .stats { color: #ccc; font-size: 22px; margin: 6px 0; }
#gameover .stats span { color: #fff; font-weight: bold; }
#gameover button {
  margin-top: 40px; width: 280px; padding: 16px;
  font-size: 20px; font-family: inherit; font-weight: bold;
  background: #c00; color: #000;
  border: none; border-radius: 4px;
  cursor: pointer; letter-spacing: 2px;
}
#gameover button:hover { background: #f00; }

#loading {
  position: absolute; inset: 0; z-index: 200;
  background: #000; display: flex;
  justify-content: center; align-items: center;
  font-size: 24px; color: #c00; letter-spacing: 4px;
}
#loading.hidden { display: none; }
</style>
</head>
<body>

<div id="loading">ЗАГРУЗКА...</div>

<div id="menu" style="display:none">
  <h1>ZOMBIE SURVIVAL</h1>
  <div class="subtitle">ВЫЖИВИ КАК МОЖНО ДОЛЬШЕ</div>
  <button id="btn-play">ИГРАТЬ</button>
  <button id="btn-settings" disabled>НАСТРОЙКИ (скоро)</button>
</div>

<div id="hud">
  <div id="hp-bar"><div id="hp-fill"></div></div>
  <div id="hp-text">100</div>
  <div id="ammo">
    <div class="weapon" id="weapon-name">ПИСТОЛЕТ</div>
    <div class="count" id="ammo-count">12</div>
    <div class="reloading" id="reloading" style="display:none">ПЕРЕЗАРЯДКА...</div>
  </div>
  <div id="score-box">
    <div class="wave">ВОЛНА <span id="wave">1</span></div>
    <div class="score">СЧЁТ <span id="score">0</span></div>
  </div>
  <div id="crosshair"></div>
  <div id="hit-marker"></div>
  <div id="damage-overlay"></div>
</div>

<div id="pause">
  <h2>ПАУЗА</h2>
  <button id="btn-resume">ПРОДОЛЖИТЬ</button>
  <button id="btn-menu">В МЕНЮ</button>
</div>

<div id="gameover">
  <h1>ВЫ ПОГИБЛИ</h1>
  <div class="stats">Волна: <span id="go-wave">1</span></div>
  <div class="stats">Счёт: <span id="go-score">0</span></div>
  <div class="stats">Убито зомби: <span id="go-kills">0</span></div>
  <button id="btn-restart">ИГРАТЬ СНОВА</button>
  <button id="btn-go-menu" style="background:transparent;color:#fff;border:2px solid #c00;margin-top:10px">В МЕНЮ</button>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js"
  }
}
</script>
<script type="module">
import * as THREE from 'three';

const CONFIG = {
  playerSpeed: 5.5,
  playerRunSpeed: 9,
  playerHeight: 1.7,
  mouseSensitivity: 0.002,
  arenaSize: 70,
  maxZombies: 12,
  waveBaseZombies: 3,
  waveZombiesPerWave: 2,
  zombieBaseSpeed: 1.8,
  zombieBaseHealth: 60,
  zombieDamage: 12,
  zombieAttackRange: 1.6,
  zombieAttackCooldown: 1000,
};

const WEAPONS = {
  pistol: {
    name: 'ПИСТОЛЕТ', damage: 34, fireRate: 280,
    magSize: 12, reloadTime: 1400, spread: 0.008,
    range: 80,
  },
};
const MELEE = {
  knife: { name: 'НОЖ', damage: 90, fireRate: 500, range: 2.2 },
};

// ============ СЦЕНА ============
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a12);
scene.fog = new THREE.Fog(0x0a0a12, 20, 90);

const camera = new THREE.PerspectiveCamera(75, innerWidth/innerHeight, 0.1, 300);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
// ФИКС: canvas должен принимать фокус клавиатуры
renderer.domElement.tabIndex = 0;

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// ============ СВЕТ ============
scene.add(new THREE.AmbientLight(0x404060, 0.6));
const moon = new THREE.DirectionalLight(0x8899ff, 0.4);
moon.position.set(30, 50, 20);
moon.castShadow = true;
moon.shadow.mapSize.set(2048, 2048);
const sc = moon.shadow.camera;
sc.left=-60; sc.right=60; sc.top=60; sc.bottom=-60;
scene.add(moon);

const lampPositions = [[-20,-20],[20,-20],[-20,20],[20,20],[0,0]];
for (const [x,z] of lampPositions) {
  const lamp = new THREE.PointLight(0xffaa55, 1.2, 25);
  lamp.position.set(x, 6, z);
  lamp.castShadow = true;
  scene.add(lamp);
  const pole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.1, 0.1, 6),
    new THREE.MeshStandardMaterial({ color: 0x333333 })
  );
  pole.position.set(x, 3, z);
  pole.castShadow = true;
  scene.add(pole);
  const bulb = new THREE.Mesh(
    new THREE.SphereGeometry(0.3, 8, 8),
    new THREE.MeshBasicMaterial({ color: 0xffaa55 })
  );
  bulb.position.set(x, 6, z);
  scene.add(bulb);
}

// ============ ПРОЦЕДУРНЫЕ ТЕКСТУРЫ ============
function makeFloorTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#3a3a3a';
  ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 3000; i++) {
    const g = 30 + Math.random() * 40;
    ctx.fillStyle = `rgb(${g},${g},${g})`;
    ctx.fillRect(Math.random()*256, Math.random()*256, 2, 2);
  }
  ctx.strokeStyle = '#1a1a1a';
  ctx.lineWidth = 1;
  for (let i = 0; i < 8; i++) {
    ctx.beginPath();
    let x = Math.random()*256, y = Math.random()*256;
    ctx.moveTo(x, y);
    for (let j = 0; j < 5; j++) {
      x += (Math.random()-0.5)*40;
      y += (Math.random()-0.5)*40;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(0,0,0,0.3)';
  ctx.lineWidth = 2;
  ctx.strokeRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(10, 10);
  return tex;
}

function makeWallTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#4a4a3a';
  ctx.fillRect(0, 0, 256, 256);
  const bw = 64, bh = 32;
  for (let y = 0; y < 256; y += bh) {
    const offset = (y / bh) % 2 === 0 ? 0 : bw/2;
    for (let x = -bw; x < 256; x += bw) {
      const g = 50 + Math.random()*30;
      ctx.fillStyle = `rgb(${g+20},${g+10},${g-10})`;
      ctx.fillRect(x+offset+2, y+2, bw-4, bh-4);
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function makeZombieTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#3a5a2a';
  ctx.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 40; i++) {
    ctx.fillStyle = `rgba(${20+Math.random()*30},${40+Math.random()*40},${20+Math.random()*20},0.7)`;
    ctx.beginPath();
    ctx.arc(Math.random()*128, Math.random()*128, 2+Math.random()*6, 0, Math.PI*2);
    ctx.fill();
  }
  ctx.fillStyle = 'rgba(100,0,0,0.6)';
  for (let i = 0; i < 10; i++) {
    ctx.beginPath();
    ctx.arc(Math.random()*128, Math.random()*128, 3+Math.random()*8, 0, Math.PI*2);
    ctx.fill();
  }
  return new THREE.CanvasTexture(c);
}

const floorTex = makeFloorTexture();
const wallTex = makeWallTexture();
const zombieTex = makeZombieTexture();

// ============ АРЕНА ============
const half = CONFIG.arenaSize / 2;
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(CONFIG.arenaSize, CONFIG.arenaSize),
  new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.95 })
);
floor.rotation.x = -Math.PI/2;
floor.receiveShadow = true;
scene.add(floor);

const colliders = [];
const wallMatBase = new THREE.MeshStandardMaterial({ map: wallTex, roughness: 0.9 });

function addWall(x, z, w, d, h=5) {
  const mat = wallMatBase.clone();
  mat.map = wallTex.clone();
  mat.map.wrapS = mat.map.wrapT = THREE.RepeatWrapping;
  mat.map.repeat.set(Math.max(1, w/4), Math.max(1, h/4));
  mat.map.needsUpdate = true;
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, h/2, z);
  m.castShadow = true; m.receiveShadow = true;
  scene.add(m);
  colliders.push({ x, z, halfW: w/2, halfD: d/2, h });
}

addWall(0, -half, CONFIG.arenaSize, 1.5);
addWall(0, half, CONFIG.arenaSize, 1.5);
addWall(-half, 0, 1.5, CONFIG.arenaSize);
addWall(half, 0, 1.5, CONFIG.arenaSize);

const layout = [
  [-18,-18,10,2], [18,-18,10,2], [-18,18,10,2], [18,18,10,2],
  [0,-14,2,10], [0,14,2,10],
  [-14,0,10,2], [14,0,10,2],
  [-8,-8,3,3], [8,8,3,3], [-8,8,3,3], [8,-8,3,3],
  [-25,0,2,14], [25,0,2,14],
  [0,0,4,4],
];
for (const [x,z,w,d] of layout) addWall(x, z, w, d, 3 + Math.random()*2);

function blockedStatic(x, z, r) {
  for (const c of colliders) {
    if (Math.abs(x-c.x) < c.halfW+r && Math.abs(z-c.z) < c.halfD+r) return true;
  }
  return false;
}

// Бочки
for (let i = 0; i < 15; i++) {
  const barrel = new THREE.Mesh(
    new THREE.CylinderGeometry(0.4, 0.4, 1.2, 12),
    new THREE.MeshStandardMaterial({ color: [0x884422, 0x446688, 0x668844][i%3], roughness: 0.8 })
  );
  let bx, bz, ok = false;
  for (let t = 0; t < 20; t++) {
    bx = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    bz = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    if (!blockedStatic(bx, bz, 0.8)) { ok = true; break; }
  }
  if (ok) {
    barrel.position.set(bx, 0.6, bz);
    barrel.castShadow = true;
    scene.add(barrel);
    colliders.push({ x: bx, z: bz, halfW: 0.4, halfD: 0.4, h: 1.2 });
  }
}

// ============ ИГРОК ============
const player = {
  pos: new THREE.Vector3(0, CONFIG.playerHeight, 0),
  yaw: 0, pitch: 0,
  health: 100, maxHealth: 100,
  weapon: 'pistol',
  ammo: 12,
  reloading: false,
  lastShot: 0,
  lastMelee: 0,
};

const weaponGroup = new THREE.Group();
const gunBody = new THREE.Mesh(
  new THREE.BoxGeometry(0.12, 0.16, 0.4),
  new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.7, roughness: 0.4 })
);
gunBody.position.set(0.25, -0.25, -0.45);
weaponGroup.add(gunBody);
const gunBarrel = new THREE.Mesh(
  new THREE.BoxGeometry(0.06, 0.06, 0.45),
  new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.8, roughness: 0.3 })
);
gunBarrel.position.set(0.25, -0.21, -0.75);
weaponGroup.add(gunBarrel);
camera.add(weaponGroup);
scene.add(camera);

const knifeGroup = new THREE.Group();
const blade = new THREE.Mesh(
  new THREE.BoxGeometry(0.04, 0.04, 0.35),
  new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.9, roughness: 0.2 })
);
blade.position.set(0.3, -0.3, -0.5);
knifeGroup.add(blade);
const handle = new THREE.Mesh(
  new THREE.BoxGeometry(0.05, 0.1, 0.15),
  new THREE.MeshStandardMaterial({ color: 0x442211, roughness: 0.9 })
);
handle.position.set(0.3, -0.32, -0.3);
knifeGroup.add(handle);
knifeGroup.visible = false;
camera.add(knifeGroup);

// ============ ВВОД ============
const keys = {};
addEventListener('keydown', e => {
  // ФИКС: не даём браузеру перехватывать игровые клавиши
  if (['KeyW','KeyA','KeyS','KeyD','Space','ShiftLeft','ShiftRight','KeyR','KeyV','Escape'].includes(e.code)) {
    e.preventDefault();
  }
  keys[e.code] = true;
  if (e.code === 'KeyR') reload();
  if (e.code === 'Digit1') switchWeapon('pistol');
  if (e.code === 'Digit2') switchWeapon('knife');
  if (e.code === 'KeyV') meleeAttack();
  if (e.code === 'Escape' && state.running) pauseGame();
});
addEventListener('keyup', e => keys[e.code] = false);

let mouseDown = false;
addEventListener('mousedown', e => {
  if (e.button === 0 && document.pointerLockElement === renderer.domElement) {
    mouseDown = true;
    if (player.weapon === 'pistol') shoot();
    else meleeAttack();
  }
});
addEventListener('mouseup', e => { if (e.button === 0) mouseDown = false; });

addEventListener('wheel', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  switchWeapon(player.weapon === 'pistol' ? 'knife' : 'pistol');
});

addEventListener('mousemove', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  player.yaw -= e.movementX * CONFIG.mouseSensitivity;
  player.pitch -= e.movementY * CONFIG.mouseSensitivity;
  player.pitch = Math.max(-Math.PI/2+0.01, Math.min(Math.PI/2-0.01, player.pitch));
});

// ============ ОРУЖИЕ ============
const raycaster = new THREE.Raycaster();
const screenCenter = new THREE.Vector2(0, 0);

function switchWeapon(w) {
  if (player.reloading) return;
  player.weapon = w;
  weaponGroup.visible = (w === 'pistol');
  knifeGroup.visible = (w === 'knife');
  updateHUD();
}

function shoot() {
  if (player.reloading || player.ammo <= 0) {
    if (player.ammo <= 0) reload();
    return;
  }
  const w = WEAPONS.pistol;
  const now = performance.now();
  if (now - player.lastShot < w.fireRate) return;
  player.lastShot = now;
  player.ammo--;
  updateHUD();

  raycaster.setFromCamera(screenCenter, camera);
  if (w.spread > 0) {
    const dir = raycaster.ray.direction.clone();
    dir.x += (Math.random()-0.5)*w.spread;
    dir.y += (Math.random()-0.5)*w.spread;
    dir.z += (Math.random()-0.5)*w.spread;
    dir.normalize();
    raycaster.ray.direction.copy(dir);
  }
  raycaster.far = w.range;

  const targets = zombies.filter(z => z.alive).map(z => z.mesh);
  const hits = raycaster.intersectObjects(targets, true);
  if (hits.length) {
    const hit = hits[0];
    let zombie = null;
    for (const z of zombies) {
      if (z.alive && (z.mesh === hit.object || z.mesh.children.includes(hit.object))) {
        zombie = z; break;
      }
    }
    if (zombie) {
      zombie.health -= w.damage;
      spawnParticles(hit.point, 0xaa0000, 10);
      showHitMarker();
      if (zombie.health <= 0) killZombie(zombie);
    }
  } else {
    const worldHits = raycaster.intersectObjects(scene.children, true);
    if (worldHits.length) spawnParticles(worldHits[0].point, 0x999999, 3);
  }
  weaponGroup.position.z = 0.06;
}

function reload() {
  if (player.reloading || player.ammo === WEAPONS.pistol.magSize) return;
  player.reloading = true;
  updateHUD();
  setTimeout(() => {
    player.ammo = WEAPONS.pistol.magSize;
    player.reloading = false;
    updateHUD();
  }, WEAPONS.pistol.reloadTime);
}

function meleeAttack() {
  const now = performance.now();
  if (now - player.lastMelee < MELEE.knife.fireRate) return;
  player.lastMelee = now;
  knifeGroup.position.z = -0.15;
  setTimeout(() => { knifeGroup.position.z = 0; }, 100);

  const forward = new THREE.Vector3(-Math.sin(player.yaw), 0, -Math.cos(player.yaw));
  for (const z of zombies) {
    if (!z.alive) continue;
    const toZombie = new THREE.Vector3().subVectors(z.mesh.position, player.pos).setY(0);
    const dist = toZombie.length();
    if (dist < MELEE.knife.range) {
      const angle = forward.angleTo(toZombie);
      if (angle < Math.PI/3) {
        z.health -= MELEE.knife.damage;
        spawnParticles(z.mesh.position.clone().setY(1), 0xaa0000, 15);
        showHitMarker();
        if (z.health <= 0) killZombie(z);
      }
    }
  }
}

// ============ ЗОМБИ ============
const zombies = [];
const zombieGeo = new THREE.BoxGeometry(0.7, 1.4, 0.5);
const zombieHeadGeo = new THREE.BoxGeometry(0.5, 0.5, 0.5);
const zombieBodyMat = new THREE.MeshStandardMaterial({ map: zombieTex, roughness: 0.9 });

function spawnZombie() {
  let x, z, tries = 0;
  do {
    x = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    z = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    tries++;
  } while ((Math.hypot(x-player.pos.x, z-player.pos.z) < 20 || blockedStatic(x, z, 1)) && tries < 80);

  const group = new THREE.Group();
  const body = new THREE.Mesh(zombieGeo, zombieBodyMat.clone());
  body.position.y = 0.7;
  body.castShadow = true;
  group.add(body);
  const head = new THREE.Mesh(zombieHeadGeo, new THREE.MeshStandardMaterial({ color: 0x6a8a4a, roughness: 0.9 }));
  head.position.y = 1.55;
  head.castShadow = true;
  group.add(head);
  const eyeMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
  const eyeL = new THREE.Mesh(new THREE.SphereGeometry(0.06, 6, 6), eyeMat);
  eyeL.position.set(-0.12, 1.6, 0.26);
  group.add(eyeL);
  const eyeR = new THREE.Mesh(new THREE.SphereGeometry(0.06, 6, 6), eyeMat);
  eyeR.position.set(0.12, 1.6, 0.26);
  group.add(eyeR);

  group.position.set(x, 0, z);
  scene.add(group);

  const waveMult = 1 + (wave-1)*0.15;
  zombies.push({
    mesh: group,
    health: CONFIG.zombieBaseHealth * waveMult,
    maxHealth: CONFIG.zombieBaseHealth * waveMult,
    speed: CONFIG.zombieBaseSpeed * (1 + (wave-1)*0.08),
    lastAttack: 0,
    alive: true,
  });
}

function killZombie(z) {
  z.alive = false;
  scene.remove(z.mesh);
  score += 50;
  kills++;
  updateHUD();
  spawnParticles(z.mesh.position.clone().setY(1), 0xaa0000, 30);
}

// ============ ЧАСТИЦЫ ============
const particles = [];
const particleGeo = new THREE.SphereGeometry(0.06, 4, 4);
function spawnParticles(pos, color, count) {
  for (let i = 0; i < count; i++) {
    const m = new THREE.Mesh(particleGeo, new THREE.MeshBasicMaterial({ color }));
    m.position.copy(pos);
    scene.add(m);
    particles.push({
      mesh: m,
      vel: new THREE.Vector3(
        (Math.random()-0.5)*7,
        Math.random()*4 + 1,
        (Math.random()-0.5)*7
      ),
      life: 0.5 + Math.random()*0.3,
    });
  }
}

// ============ HUD ============
let score = 0, kills = 0, wave = 1;
let zombiesToSpawn = CONFIG.waveBaseZombies;
let waveActive = false;
let waveDelayTimer = 0;

const hudEl = document.getElementById('hud');
const hpFill = document.getElementById('hp-fill');
const hpText = document.getElementById('hp-text');
const ammoCount = document.getElementById('ammo-count');
const weaponName = document.getElementById('weapon-name');
const reloadingEl = document.getElementById('reloading');
const waveEl = document.getElementById('wave');
const scoreEl = document.getElementById('score');
const hitMarker = document.getElementById('hit-marker');
const damageOverlay = document.getElementById('damage-overlay');

function updateHUD() {
  hpFill.style.width = Math.max(0, player.health) + '%';
  hpText.textContent = Math.max(0, Math.round(player.health));
  ammoCount.textContent = player.reloading ? '...' : player.ammo;
  ammoCount.classList.toggle('low', player.ammo <= 3);
  weaponName.textContent = player.weapon === 'pistol' ? WEAPONS.pistol.name : MELEE.knife.name;
  reloadingEl.style.display = player.reloading ? 'block' : 'none';
  waveEl.textContent = wave;
  scoreEl.textContent = score;
}

function showHitMarker() {
  hitMarker.style.opacity = '1';
  setTimeout(() => hitMarker.style.opacity = '0', 120);
}

function flashDamage() {
  damageOverlay.classList.add('hit');
  setTimeout(() => damageOverlay.classList.remove('hit'), 200);
}

// ============ СОСТОЯНИЕ ============
const state = {
  running: false,
  paused: false,
};

// ============ ЦИКЛ ============
let lastTime = performance.now();

function update(dt) {
  if (!state.running || state.paused) return;

  const speed = (keys['ShiftLeft'] || keys['ShiftRight']) ? CONFIG.playerRunSpeed : CONFIG.playerSpeed;
  const fwd = new THREE.Vector3(-Math.sin(player.yaw), 0, -Math.cos(player.yaw));
  const right = new THREE.Vector3(Math.cos(player.yaw), 0, -Math.sin(player.yaw));
  const move = new THREE.Vector3();
  if (keys['KeyW']) move.add(fwd);
  if (keys['KeyS']) move.sub(fwd);
  if (keys['KeyD']) move.add(right);
  if (keys['KeyA']) move.sub(right);
  if (move.lengthSq() > 0) {
    move.normalize().multiplyScalar(speed * dt);
    const nx = player.pos.x + move.x;
    const nz = player.pos.z + move.z;
    if (!blockedStatic(nx, player.pos.z, 0.5) && Math.abs(nx) < half-1.5) player.pos.x = nx;
    if (!blockedStatic(player.pos.x, nz, 0.5) && Math.abs(nz) < half-1.5) player.pos.z = nz;
  }

  camera.position.copy(player.pos);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = player.yaw;
  camera.rotation.x = player.pitch;

  weaponGroup.position.z += (0 - weaponGroup.position.z) * dt * 12;
  knifeGroup.position.z += (0 - knifeGroup.position.z) * dt * 12;

  if (mouseDown && player.weapon === 'pistol') shoot();

  if (!waveActive && zombiesToSpawn <= 0 && zombies.filter(z => z.alive).length === 0) {
    waveDelayTimer += dt;
    if (waveDelayTimer > 2) {
      wave++;
      zombiesToSpawn = CONFIG.waveBaseZombies + (wave-1)*CONFIG.waveZombiesPerWave;
      waveActive = true;
      waveDelayTimer = 0;
      updateHUD();
    }
  }

  if (waveActive && zombiesToSpawn > 0) {
    const spawnInterval = Math.max(0.3, 1.2 - wave*0.05);
    if (performance.now() - (state.lastSpawn || 0) > spawnInterval*1000) {
      state.lastSpawn = performance.now();
      const aliveCount = zombies.filter(z => z.alive).length;
      if (aliveCount < CONFIG.maxZombies) {
        spawnZombie();
        zombiesToSpawn--;
      }
    }
    if (zombiesToSpawn <= 0) waveActive = false;
  }

  const now = performance.now();
  for (const z of zombies) {
    if (!z.alive) continue;
    const dir = new THREE.Vector3().subVectors(player.pos, z.mesh.position).setY(0);
    const dist = dir.length();
    if (dist > 0.1) {
      dir.normalize();
      if (dist > CONFIG.zombieAttackRange) {
        const step = z.speed * dt;
        const nx = z.mesh.position.x + dir.x * step;
        const nz = z.mesh.position.z + dir.z * step;
        if (!blockedStatic(nx, z.mesh.position.z, 0.5)) z.mesh.position.x = nx;
        if (!blockedStatic(z.mesh.position.x, nz, 0.5)) z.mesh.position.z = nz;
      }
      z.mesh.rotation.y = Math.atan2(dir.x, dir.z);
    }
    if (dist < CONFIG.zombieAttackRange && now - z.lastAttack > CONFIG.zombieAttackCooldown) {
      z.lastAttack = now;
      player.health -= CONFIG.zombieDamage;
      flashDamage();
      updateHUD();
      if (player.health <= 0) {
        player.health = 0;
        gameOver();
      }
    }
  }

  for (let i = particles.length-1; i >= 0; i--) {
    const p = particles[i];
    p.vel.y -= 12*dt;
    p.mesh.position.addScaledVector(p.vel, dt);
    p.life -= dt;
    if (p.life <= 0) {
      scene.remove(p.mesh);
      particles.splice(i, 1);
    }
  }
}

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const dt = Math.min((now - lastTime)/1000, 0.05);
  lastTime = now;
  update(dt);
  renderer.render(scene, camera);
}

// ============ УПРАВЛЕНИЕ ИГРОЙ ============
const menuEl = document.getElementById('menu');
const pauseEl = document.getElementById('pause');
const gameoverEl = document.getElementById('gameover');
const loadingEl = document.getElementById('loading');

function startGame() {
  player.pos.set(0, CONFIG.playerHeight, 0);
  player.yaw = 0; player.pitch = 0;
  player.health = player.maxHealth;
  player.ammo = WEAPONS.pistol.magSize;
  player.weapon = 'pistol';
  player.reloading = false;
  weaponGroup.visible = true;
  knifeGroup.visible = false;
  score = 0; kills = 0; wave = 1;
  zombiesToSpawn = CONFIG.waveBaseZombies;
  waveActive = true;
  waveDelayTimer = 0;
  state.running = true;
  state.paused = false;
  state.lastSpawn = 0;

  for (const z of zombies) if (z.alive) scene.remove(z.mesh);
  zombies.length = 0;
  for (const p of particles) scene.remove(p.mesh);
  particles.length = 0;

  menuEl.style.display = 'none';
  pauseEl.classList.remove('active');
  gameoverEl.classList.remove('active');
  hudEl.classList.add('active');

  updateHUD();

  // ФИКС ДВИЖЕНИЯ: фокус на canvas перед pointer lock
  renderer.domElement.focus();
  renderer.domElement.requestPointerLock();

  lastTime = performance.now();
}

function pauseGame() {
  if (!state.running || state.paused) return;
  state.paused = true;
  document.exitPointerLock();
  pauseEl.classList.add('active');
}

function resumeGame() {
  state.paused = false;
  pauseEl.classList.remove('active');
  // ФИКС: вернуть фокус на canvas
  renderer.domElement.focus();
  renderer.domElement.requestPointerLock();
  lastTime = performance.now();
}

function gameOver() {
  state.running = false;
  document.exitPointerLock();
  document.getElementById('go-wave').textContent = wave;
  document.getElementById('go-score').textContent = score;
  document.getElementById('go-kills').textContent = kills;
  gameoverEl.classList.add('active');
  hudEl.classList.remove('active');

  fetch('/api/scores', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'Player', score })
  }).catch(() => {});
}

function backToMenu() {
  state.running = false;
  state.paused = false;
  document.exitPointerLock();
  hudEl.classList.remove('active');
  pauseEl.classList.remove('active');
  gameoverEl.classList.remove('active');
  menuEl.style.display = 'flex';
}

// ============ КНОПКИ ============
document.getElementById('btn-play').addEventListener('click', startGame);
document.getElementById('btn-resume').addEventListener('click', resumeGame);
document.getElementById('btn-menu').addEventListener('click', backToMenu);
document.getElementById('btn-restart').addEventListener('click', startGame);
document.getElementById('btn-go-menu').addEventListener('click', backToMenu);

document.addEventListener('pointerlockchange', () => {
  if (document.pointerLockElement !== renderer.domElement && state.running && !state.paused) {
    pauseGame();
  }
});

// ============ СТАРТ ============
loadingEl.classList.add('hidden');
menuEl.style.display = 'flex';
updateHUD();
animate();
</script>
</body>
</html>
"""

# ============ РОУТЫ ============

@app.route('/')
def index():
    return Response(INDEX_HTML, mimetype='text/html')

@app.route('/health')
@json_endpoint
def health():
    return {'status': 'ok', 'time': time.time()}

@app.route('/api/scores', methods=['GET'])
@json_endpoint
def get_scores():
    scores = load_scores()
    scores.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'count': len(scores), 'scores': scores[:TOP_N]}

@app.route('/api/scores', methods=['POST'])
@require_json
@json_endpoint
def post_score():
    ip = request.remote_addr or 'unknown'
    if rate_limited(ip):
        return jsonify({'error': 'rate_limited'}), 429

    data = request.get_json(silent=True) or {}
    name = str(data.get('name', 'Anonymous')).strip()[:MAX_NAME_LEN] or 'Anonymous'
    try:
        score = int(data.get('score', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid_score'}), 400

    if score < 0 or score > 10_000_000:
        return jsonify({'error': 'score_out_of_range'}), 400

    with file_lock:
        scores = load_scores()
        scores.append({'name': name, 'score': score, 'date': time.strftime('%Y-%m-%d %H:%M:%S')})
        scores.sort(key=lambda x: x.get('score', 0), reverse=True)
        scores = scores[:MAX_SCORES]
        save_scores(scores)

    rank = next((i+1 for i,s in enumerate(scores) if s['score']==score and s['name']==name), None)
    return {'ok': True, 'rank': rank}

@app.errorhandler(404)
def not_found(e): return Response(INDEX_HTML, mimetype='text/html')

if __name__ == '__main__':
    log.info(f'Запуск на порту {PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG, threaded=True)
  
