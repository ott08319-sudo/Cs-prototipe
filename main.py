"""
CS Prototype — всё в одном файле.
Flask-сервер + HTML + CSS + JS (Three.js) в одном main.py.
Запуск: python main.py
"""
from flask import Flask, send_from_directory, jsonify, request, abort, Response
import os
import json
import time
import logging
from functools import wraps
from threading import Lock

# ============ КОНФИГ ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_FILE = os.path.join(BASE_DIR, 'scores.json')
STATS_FILE = os.path.join(BASE_DIR, 'stats.json')
MAX_SCORES = 100
TOP_N = 10
MAX_NAME_LEN = 20
RATE_LIMIT_SECONDS = 2
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('cs-server')

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
def load_stats():
    return _load_json(STATS_FILE, {
        'total_games': 0, 'total_score': 0, 'best_score': 0,
        'started_at': time.time(),
    })
def save_stats(s): return _save_json(STATS_FILE, s)

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

# ============ HTML / CSS / JS ВСТРОЕНЫ ============

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CS Prototype — Extended</title>
<style>
* { box-sizing: border-box; }
body {
  margin: 0; overflow: hidden; background: #000;
  font-family: 'Courier New', monospace; color: #0f0;
}
canvas { display: block; }
#hud {
  position: absolute; bottom: 20px; left: 20px;
  font-size: 18px; text-shadow: 1px 1px 3px #000;
  pointer-events: none; user-select: none; line-height: 1.5;
}
#weapon-row { color: #ffaa00; margin-top: 6px; }
#crosshair {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 22px; height: 22px; pointer-events: none;
}
#crosshair::before, #crosshair::after {
  content: ''; position: absolute; background: #0f0;
}
#crosshair::before { width: 2px; height: 22px; left: 10px; top: 0; }
#crosshair::after { width: 22px; height: 2px; left: 0; top: 10px; }
#damage-overlay {
  position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(circle, transparent 40%, rgba(255,0,0,0.6) 100%);
  opacity: 0; transition: opacity 0.2s;
}
#damage-overlay.hit { opacity: 1; }
#overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.9);
  display: flex; flex-direction: column;
  justify-content: center; align-items: center;
  color: #fff; text-align: center; cursor: pointer;
}
#overlay h1 { font-size: 48px; margin: 0 0 20px; color: #0f0; }
#overlay p { font-size: 18px; margin: 6px 0; color: #ccc; }
#overlay .btn {
  margin-top: 28px; padding: 14px 44px;
  font-size: 22px; background: #0f0; color: #000;
  border: none; border-radius: 4px; cursor: pointer;
  font-weight: bold; font-family: inherit;
}
#overlay .btn:hover { background: #0c0; }
.hidden { display: none !important; }
</style>
</head>
<body>
<div id="hud">
  <div>HP: <span id="hp">100</span></div>
  <div>Счёт: <span id="score">0</span></div>
  <div>Волна: <span id="wave">1</span></div>
  <div id="weapon-row">
    Оружие: <span id="weapon-name">Пистолет</span>
    (<span id="ammo">12</span>/<span id="mag">12</span>)
  </div>
</div>
<div id="crosshair"></div>
<div id="damage-overlay"></div>
<div id="overlay">
  <h1>CS PROTOTYPE</h1>
  <p>WASD — движение, мышь — обзор, ЛКМ — стрельба</p>
  <p>1/2/3/4 или колесо — смена оружия, R — перезарядка, Shift — бег</p>
  <p>Уничтожайте ботов. С каждой волной они умнее и злее.</p>
  <button class="btn" id="startBtn">НАЧАТЬ</button>
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
  playerSpeed: 6, playerRunSpeed: 10, playerHeight: 1.7,
  mouseSensitivity: 0.002, arenaSize: 60, maxEnemies: 8, waveDuration: 30,
};

const WEAPONS = {
  pistol:  { name: 'Пистолет',  damage: 25,  fireRate: 250,  magSize: 12, reloadTime: 1200, spread: 0.01 },
  rifle:   { name: 'Автомат',   damage: 20,  fireRate: 90,   magSize: 30, reloadTime: 2000, spread: 0.03 },
  shotgun: { name: 'Дробовик',  damage: 12,  fireRate: 700,  magSize: 6,  reloadTime: 2500, spread: 0.15, pellets: 8, range: 25 },
  sniper:  { name: 'Снайперка', damage: 120, fireRate: 1500, magSize: 5,  reloadTime: 3000, spread: 0.001 },
};
const WEAPON_ORDER = ['pistol','rifle','shotgun','sniper'];

const ENEMY_TYPES = {
  grunt:  { health: 80,  speed: 2.5, damage: 8,  fireRate: 1000, color: 0xcc2222, headColor: 0xffcc99, scale: 1 },
  rusher: { health: 40,  speed: 5,   damage: 12, fireRate: 1500, color: 0xff4400, headColor: 0xff8800, scale: 0.8 },
  tank:   { health: 250, speed: 1.2, damage: 20, fireRate: 1400, color: 0x662222, headColor: 0xaa3333, scale: 1.4 },
  sniper: { health: 60,  speed: 1.8, damage: 25, fireRate: 2200, color: 0x8822aa, headColor: 0xbb88ff, scale: 1.1, range: 40 },
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87ceeb);
scene.fog = new THREE.Fog(0x87ceeb, 40, 100);

const camera = new THREE.PerspectiveCamera(75, innerWidth/innerHeight, 0.1, 300);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 0.9));
const sun = new THREE.DirectionalLight(0xffffff, 0.8);
sun.position.set(30, 50, 20);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
const sc = sun.shadow.camera;
sc.left=-80; sc.right=80; sc.top=80; sc.bottom=-80;
scene.add(sun);

const half = CONFIG.arenaSize/2;
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(CONFIG.arenaSize, CONFIG.arenaSize),
  new THREE.MeshStandardMaterial({ color: 0x505050 })
);
floor.rotation.x = -Math.PI/2; floor.receiveShadow = true;
scene.add(floor);

const wallMat = new THREE.MeshStandardMaterial({ color: 0x888877 });
const colliders = [];
function addBox(x, z, w, d, h=5, color) {
  const mat = color ? new THREE.MeshStandardMaterial({ color }) : wallMat;
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, h/2, z);
  m.castShadow = true; m.receiveShadow = true;
  scene.add(m);
  colliders.push({ x, z, halfW: w/2, halfD: d/2, h });
  return m;
}
addBox(0, -half, CONFIG.arenaSize, 1);
addBox(0,  half, CONFIG.arenaSize, 1);
addBox(-half, 0, 1, CONFIG.arenaSize);
addBox( half, 0, 1, CONFIG.arenaSize);
const layout = [
  [-15,-15,6,2],[15,-15,6,2],[-15,15,6,2],[15,15,6,2],
  [0,-10,2,8],[0,10,2,8],[-10,0,8,2],[10,0,8,2],
  [0,0,3,3],[-20,0,2,12],[20,0,2,12],
];
for (const [x,z,w,d] of layout) addBox(x, z, w, d, 4 + Math.random()*2);

const player = {
  pos: new THREE.Vector3(0, CONFIG.playerHeight, 0),
  yaw: 0, pitch: 0, health: 100, maxHealth: 100,
  currentWeapon: 'pistol',
  ammo: { pistol:12, rifle:30, shotgun:6, sniper:5 },
  reloading: false, lastShot: 0,
};

const viewModel = new THREE.Group();
const vmBody = new THREE.Mesh(
  new THREE.BoxGeometry(0.12,0.16,0.45),
  new THREE.MeshStandardMaterial({ color: 0x333333 })
);
vmBody.position.set(0.28,-0.28,-0.5);
viewModel.add(vmBody);
const vmBarrel = new THREE.Mesh(
  new THREE.BoxGeometry(0.06,0.06,0.55),
  new THREE.MeshStandardMaterial({ color: 0x222222 })
);
vmBarrel.position.set(0.28,-0.23,-0.85);
viewModel.add(vmBarrel);
camera.add(viewModel);
scene.add(camera);

const keys = {};
addEventListener('keydown', e => {
  keys[e.code] = true;
  if (e.code==='KeyR') reload();
  if (e.code==='Digit1') switchWeapon('pistol');
  if (e.code==='Digit2') switchWeapon('rifle');
  if (e.code==='Digit3') switchWeapon('shotgun');
  if (e.code==='Digit4') switchWeapon('sniper');
});
addEventListener('keyup', e => keys[e.code] = false);

let mouseDown = false;
addEventListener('mousedown', e => {
  if (e.button===0 && document.pointerLockElement===renderer.domElement) {
    mouseDown = true; shoot();
  }
});
addEventListener('mouseup', e => { if (e.button===0) mouseDown=false; });

addEventListener('wheel', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  const idx = WEAPON_ORDER.indexOf(player.currentWeapon);
  const next = (idx + (e.deltaY>0?1:-1) + WEAPON_ORDER.length) % WEAPON_ORDER.length;
  switchWeapon(WEAPON_ORDER[next]);
});

addEventListener('mousemove', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  player.yaw -= e.movementX * CONFIG.mouseSensitivity;
  player.pitch -= e.movementY * CONFIG.mouseSensitivity;
  player.pitch = Math.max(-Math.PI/2+0.01, Math.min(Math.PI/2-0.01, player.pitch));
});

const raycaster = new THREE.Raycaster();
const screenCenter = new THREE.Vector2(0,0);

function switchWeapon(name) {
  if (player.reloading) return;
  player.currentWeapon = name;
  updateHUD();
}

function shoot() {
  const w = WEAPONS[player.currentWeapon];
  if (player.reloading || player.ammo[player.currentWeapon] <= 0) {
    if (player.ammo[player.currentWeapon] <= 0) reload();
    return;
  }
  const now = performance.now();
  if (now - player.lastShot < w.fireRate) return;
  player.lastShot = now;
  player.ammo[player.currentWeapon]--;
  updateHUD();

  const pellets = w.pellets || 1;
  for (let i=0; i<pellets; i++) {
    raycaster.setFromCamera(screenCenter, camera);
    if (w.spread > 0) {
      const dir = raycaster.ray.direction.clone();
      dir.x += (Math.random()-0.5)*w.spread;
      dir.y += (Math.random()-0.5)*w.spread;
      dir.z += (Math.random()-0.5)*w.spread;
      dir.normalize();
      raycaster.ray.direction.copy(dir);
    }
    if (w.range) raycaster.far = w.range;
    else raycaster.far = Infinity;

    const targets = enemies.filter(e=>e.alive).map(e=>e.mesh);
    const hits = raycaster.intersectObjects(targets, true);
    if (hits.length) {
      const hit = hits[0];
      let enemy = null;
      for (const e of enemies) {
        if (e.alive && (e.mesh===hit.object || e.mesh.children.includes(hit.object))) {
          enemy = e; break;
        }
      }
      if (enemy) {
        enemy.health -= w.damage;
        spawnHitParticles(hit.point, 0xff0000, 8);
        if (enemy.health <= 0) killEnemy(enemy);
      }
    } else {
      const worldHits = raycaster.intersectObjects(scene.children, true);
      if (worldHits.length) spawnHitParticles(worldHits[0].point, 0xffffff, 3);
    }
  }
  viewModel.position.z = 0.08;
}

function reload() {
  if (player.reloading) return;
  const w = WEAPONS[player.currentWeapon];
  if (player.ammo[player.currentWeapon] >= w.magSize) return;
  player.reloading = true;
  updateHUD();
  setTimeout(() => {
    player.ammo[player.currentWeapon] = w.magSize;
    player.reloading = false;
    updateHUD();
  }, w.reloadTime);
}

const enemies = [];
const enemyBullets = [];
const bulletGeo = new THREE.SphereGeometry(0.18, 6, 6);
const bulletMat = new THREE.MeshBasicMaterial({ color: 0xffaa00 });

function blocked(x, z, r) {
  for (const c of colliders) {
    if (Math.abs(x-c.x) < c.halfW+r && Math.abs(z-c.z) < c.halfD+r) return true;
  }
  return false;
}

function spawnEnemy(typeKey) {
  const t = ENEMY_TYPES[typeKey];
  let x, z, tries = 0;
  do {
    x = (Math.random()-0.5)*(CONFIG.arenaSize-6);
    z = (Math.random()-0.5)*(CONFIG.arenaSize-6);
    tries++;
  } while ((Math.hypot(x-player.pos.x, z-player.pos.z) < 18 || blocked(x,z,1)) && tries < 50);

  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.6, 1.2, 0.4),
    new THREE.MeshStandardMaterial({ color: t.color })
  );
  body.position.y = 0.6*t.scale; body.scale.setScalar(t.scale); body.castShadow = true;
  group.add(body);
  const head = new THREE.Mesh(
    new THREE.BoxGeometry(0.4,0.4,0.4),
    new THREE.MeshStandardMaterial({ color: t.headColor })
  );
  head.position.y = 1.5*t.scale; head.scale.setScalar(t.scale); head.castShadow = true;
  group.add(head);
  group.position.set(x, 0, z);
  scene.add(group);
  enemies.push({
    type: typeKey, mesh: group,
    health: t.health, maxHealth: t.health,
    lastShot: 0, alive: true,
    strafeDir: Math.random()<0.5?1:-1, strafeTimer: 0,
  });
}

function killEnemy(enemy) {
  enemy.alive = false;
  scene.remove(enemy.mesh);
  score += 100;
  updateHUD();
  spawnHitParticles(enemy.mesh.position.clone().setY(1.2), 0xff4400, 25);
  const idx = enemies.indexOf(enemy);
  if (idx>=0) enemies.splice(idx, 1);
}

const particles = [];
function spawnHitParticles(pos, color=0xffaa00, count=8) {
  for (let i=0; i<count; i++) {
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(0.06,4,4),
      new THREE.MeshBasicMaterial({ color })
    );
    m.position.copy(pos);
    scene.add(m);
    particles.push({
      mesh: m,
      vel: new THREE.Vector3(
        (Math.random()-0.5)*8, Math.random()*5+1, (Math.random()-0.5)*8
      ),
      life: 0.6,
    });
  }
}

let score = 0, wave = 1;
const hpEl = document.getElementById('hp');
const scoreEl = document.getElementById('score');
const waveEl = document.getElementById('wave');
const weaponNameEl = document.getElementById('weapon-name');
const ammoEl = document.getElementById('ammo');
const magEl = document.getElementById('mag');
const damageOverlay = document.getElementById('damage-overlay');

function updateHUD() {
  hpEl.textContent = Math.max(0, Math.round(player.health));
  scoreEl.textContent = score;
  waveEl.textContent = wave;
  const w = WEAPONS[player.currentWeapon];
  weaponNameEl.textContent = w.name;
  ammoEl.textContent = player.reloading ? '...' : player.ammo[player.currentWeapon];
  magEl.textContent = w.magSize;
}

function flashDamage() {
  damageOverlay.classList.add('hit');
  setTimeout(() => damageOverlay.classList.remove('hit'), 200);
}

let running = false;
let lastTime = performance.now();
let overlayEl, startBtn;
let waveTimer = performance.now();

function update(dt) {
  if (!running) return;

  const speed = (keys['ShiftLeft']||keys['ShiftRight']) ? CONFIG.playerRunSpeed : CONFIG.playerSpeed;
  const fwd = new THREE.Vector3(-Math.sin(player.yaw),0,-Math.cos(player.yaw));
  const right = new THREE.Vector3(Math.cos(player.yaw),0,-Math.sin(player.yaw));
  const move = new THREE.Vector3();
  if (keys['KeyW']) move.add(fwd);
  if (keys['KeyS']) move.sub(fwd);
  if (keys['KeyD']) move.add(right);
  if (keys['KeyA']) move.sub(right);
  if (move.lengthSq() > 0) {
    move.normalize().multiplyScalar(speed*dt);
    const nx = player.pos.x + move.x;
    const nz = player.pos.z + move.z;
    if (!blocked(nx, player.pos.z, 0.5) && Math.abs(nx) < half-1) player.pos.x = nx;
    if (!blocked(player.pos.x, nz, 0.5) && Math.abs(nz) < half-1) player.pos.z = nz;
  }

  camera.position.copy(player.pos);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = player.yaw;
  camera.rotation.x = player.pitch;

  viewModel.position.z += (0 - viewModel.position.z) * dt * 15;

  if (mouseDown) shoot();

  if (performance.now() - waveTimer > CONFIG.waveDuration*1000) {
    waveTimer = performance.now();
    wave++;
    updateHUD();
  }

  const now = performance.now();
  for (const e of enemies) {
    if (!e.alive) continue;
    const t = ENEMY_TYPES[e.type];
    const dir = new THREE.Vector3().subVectors(player.pos, e.mesh.position).setY(0);
    const dist = dir.length();
    if (dist > 0.1) {
      dir.normalize();
      if (dist > 2) e.mesh.position.addScaledVector(dir, t.speed*dt);
      e.mesh.rotation.y = Math.atan2(dir.x, dir.z);
    }
    if (dist < (t.range||35) && now - e.lastShot > t.fireRate) {
      e.lastShot = now;
      const bullet = new THREE.Mesh(bulletGeo, bulletMat);
      bullet.position.copy(e.mesh.position).setY(1.2*t.scale);
      const shootDir = new THREE.Vector3().subVectors(player.pos, bullet.position).normalize();
      shootDir.x += (Math.random()-0.5)*0.08;
      shootDir.z += (Math.random()-0.5)*0.08;
      shootDir.normalize();
      scene.add(bullet);
      enemyBullets.push({ mesh: bullet, dir: shootDir, life: 3, damage: t.damage });
    }
  }

  for (let i = enemyBullets.length-1; i>=0; i--) {
    const b = enemyBullets[i];
    b.mesh.position.addScaledVector(b.dir, 40*dt);
    b.life -= dt;
    if (b.mesh.position.distanceTo(player.pos) < 0.6) {
      player.health -= b.damage;
      updateHUD();
      flashDamage();
      scene.remove(b.mesh);
      enemyBullets.splice(i, 1);
      if (player.health <= 0) gameOver();
      continue;
    }
    if (Math.abs(b.mesh.position.x) > half || Math.abs(b.mesh.position.z) > half || b.life <= 0) {
      scene.remove(b.mesh);
      enemyBullets.splice(i, 1);
    }
  }

  for (let i = particles.length-1; i>=0; i--) {
    const p = particles[i];
    p.vel.y -= 15*dt;
    p.mesh.position.addScaledVector(p.vel, dt);
    p.life -= dt;
    if (p.life <= 0) { scene.remove(p.mesh); particles.splice(i, 1); }
  }

  const alive = enemies.filter(e=>e.alive).length;
  if (alive < CONFIG.maxEnemies && Math.random() < dt*0.5) {
    const types = ['grunt','grunt','grunt','rusher','tank'];
    if (wave > 2) types.push('sniper');
    spawnEnemy(types[Math.floor(Math.random()*types.length)]);
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

async function gameOver() {
  running = false;
  document.exitPointerLock();
  overlayEl.classList.remove('hidden');
  overlayEl.querySelector('h1').textContent = 'ВЫ ПОГИБЛИ';
  overlayEl.querySelector('.btn').textContent = 'ЗАНОВО';
  overlayEl.querySelectorAll('p')[0].textContent = `Ваш счёт: ${score}`;
  overlayEl.querySelectorAll('p')[1].textContent = 'Отправка результата...';
  try {
    const r = await fetch('/api/scores', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Player', score })
    });
    const data = await r.json();
    overlayEl.querySelectorAll('p')[1].textContent =
      data.rank ? `Ваш ранг: #${data.rank}` : 'Результат сохранён';
  } catch (err) {
    overlayEl.querySelectorAll('p')[1].textContent = 'Не удалось сохранить результат';
  }
}

overlayEl = document.getElementById('overlay');
startBtn = document.getElementById('startBtn');

function startGame() {
  player.pos.set(0, CONFIG.playerHeight, 0);
  player.yaw = 0; player.pitch = 0;
  player.health = player.maxHealth;
  player.ammo = { pistol:12, rifle:30, shotgun:6, sniper:5 };
  player.currentWeapon = 'pistol';
  player.reloading = false;
  score = 0; wave = 1;
  waveTimer = performance.now();
  updateHUD();

  for (const e of enemies) if (e.alive) scene.remove(e.mesh);
  enemies.length = 0;
  for (const b of enemyBullets) scene.remove(b.mesh);
  enemyBullets.length = 0;
  for (const p of particles) scene.remove(p.mesh);
  particles.length = 0;

  overlayEl.classList.add('hidden');
  renderer.domElement.requestPointerLock();
  running = true;
  lastTime = performance.now();
  for (let i=0; i<3; i++) spawnEnemy('grunt');
}

startBtn.addEventListener('click', startGame);

document.addEventListener('pointerlockchange', () => {
  if (document.pointerLockElement !== renderer.domElement && running) {
    running = false;
    overlayEl.classList.remove('hidden');
    overlayEl.querySelector('h1').textContent = 'ПАУЗА';
    overlayEl.querySelector('.btn').textContent = 'ПРОДОЛЖИТЬ';
  }
});

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
    return {
        'status': 'ok',
        'uptime': round(time.time() - load_stats().get('started_at', time.time()), 1),
        'scores_count': len(load_scores()),
        'debug': DEBUG,
    }

@app.route('/api/info')
@json_endpoint
def info():
    return {
        'name': 'CS Prototype',
        'version': '1.0.0',
        'max_scores': MAX_SCORES,
        'top_n': TOP_N,
        'endpoints': [
            'GET  /health',
            'GET  /api/info',
            'GET  /api/scores',
            'GET  /api/scores/top',
            'POST /api/scores',
            'GET  /api/stats',
        ],
    }

@app.route('/api/scores', methods=['GET'])
@json_endpoint
def get_scores():
    scores = load_scores()
    scores.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'count': len(scores), 'scores': scores[:TOP_N]}

@app.route('/api/scores/top', methods=['GET'])
@json_endpoint
def get_top_scores():
    scores = load_scores()
    scores.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'top': scores[:3]}

@app.route('/api/scores', methods=['POST'])
@require_json
@json_endpoint
def post_score():
    ip = request.remote_addr or 'unknown'
    if rate_limited(ip):
        return jsonify({'error': 'rate_limited', 'retry_after': RATE_LIMIT_SECONDS}), 429

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
        entry = {
            'name': name, 'score': score,
            'date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'ip_hash': str(hash(ip))[:8],
        }
        scores.append(entry)
        scores.sort(key=lambda x: x.get('score', 0), reverse=True)
        scores = scores[:MAX_SCORES]
        save_scores(scores)

        stats = load_stats()
        stats['total_games'] = stats.get('total_games', 0) + 1
        stats['total_score'] = stats.get('total_score', 0) + score
        stats['best_score'] = max(stats.get('best_score', 0), score)
        save_stats(stats)

    rank = next((i+1 for i,s in enumerate(scores)
                 if s['score']==score and s['name']==name), None)
    log.info(f'Новый результат: {name} — {score} (ранг {rank})')
    return {'ok': True, 'rank': rank, 'best': scores[0]['score'] if scores else score}

@app.route('/api/stats')
@json_endpoint
def get_stats():
    stats = load_stats()
    scores = load_scores()
    avg = round(stats['total_score']/stats['total_games'], 1) if stats['total_games'] else 0
    return {
        'total_games': stats.get('total_games', 0),
        'best_score': stats.get('best_score', 0),
        'average_score': avg,
        'players_in_board': len(scores),
        'uptime': round(time.time() - stats.get('started_at', time.time()), 1),
    }

@app.errorhandler(403)
def forbidden(e): return jsonify({'error': 'forbidden'}), 403

@app.errorhandler(404)
def not_found(e): return Response(INDEX_HTML, mimetype='text/html')

@app.errorhandler(405)
def method_not_allowed(e): return jsonify({'error': 'method_not_allowed'}), 405

@app.errorhandler(500)
def server_error(e): return jsonify({'error': 'internal_server_error'}), 500

if __name__ == '__main__':
    log.info(f'Запуск на порту {PORT} (debug={DEBUG})')
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG, threaded=True)
