"""
Zombie Survival — полная версия с фиксами.
Фиксы: зомби не застревают в коллайдерах, WASD работает надёжнее.
Запуск: python main.py
"""
from flask import Flask, jsonify, request, Response
import os, json, time, logging
from functools import wraps
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORES_FILE = os.path.join(BASE_DIR, 'scores.json')
MAX_SCORES = 100
TOP_N = 10
MAX_NAME_LEN = 20
RATE_LIMIT_SECONDS = 2
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))

logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger('zombie-server')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
file_lock = Lock()
last_post_by_ip = {}

def rate_limited(ip):
    now = time.time()
    last = last_post_by_ip.get(ip, 0)
    if now - last < RATE_LIMIT_SECONDS: return True
    last_post_by_ip[ip] = now
    return False

def _load_json(path, default):
    if not os.path.exists(path): return default
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        log.warning(f'Не удалось прочитать {path}: {e}'); return default

def _save_json(path, data):
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path); return True
    except Exception as e:
        log.error(f'Не удалось сохранить {path}: {e}'); return False

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
        if not request.is_json: return jsonify({'error': 'json_required'}), 400
        return fn(*a, **kw)
    return wrapper

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zombie Survival</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { overflow: hidden; background: #000; font-family: 'Courier New', monospace; color: #fff; user-select: none; outline: none; }
canvas { display: block; outline: none; }

#menu { position: absolute; inset: 0; z-index: 100; background: linear-gradient(135deg, #1a0000 0%, #000 100%); display: flex; flex-direction: column; justify-content: center; align-items: center; overflow-y: auto; padding: 20px; }
#menu h1 { font-size: 64px; color: #c00; letter-spacing: 4px; text-shadow: 0 0 30px #f00, 0 0 60px #900; margin-bottom: 8px; }
#menu .subtitle { color: #888; font-size: 16px; margin-bottom: 30px; letter-spacing: 2px; }
#menu .section-title { color: #f80; font-size: 14px; letter-spacing: 3px; margin: 20px 0 10px; }
#menu button { width: 340px; padding: 16px; margin: 6px; font-size: 20px; font-family: inherit; font-weight: bold; background: transparent; color: #fff; border: 2px solid #c00; border-radius: 4px; cursor: pointer; transition: all 0.2s; letter-spacing: 2px; }
#menu button:hover { background: #c00; color: #000; box-shadow: 0 0 20px #f00; }

#settings { position: absolute; inset: 0; z-index: 110; background: rgba(0,0,0,0.95); display: none; flex-direction: column; justify-content: center; align-items: center; }
#settings.active { display: flex; }
#settings h2 { font-size: 48px; color: #c00; margin-bottom: 30px; letter-spacing: 4px; }
#settings .row { width: 400px; margin: 14px 0; }
#settings label { display: block; color: #ccc; font-size: 16px; margin-bottom: 6px; letter-spacing: 1px; }
#settings input[type=range] { width: 100%; }
#settings .val { color: #f80; font-weight: bold; }
#settings button { margin-top: 30px; width: 280px; padding: 14px; font-size: 18px; font-family: inherit; font-weight: bold; background: #c00; color: #000; border: none; border-radius: 4px; cursor: pointer; letter-spacing: 2px; }
#settings button:hover { background: #f00; }

#hud { position: absolute; inset: 0; pointer-events: none; display: none; z-index: 10; }
#hud.active { display: block; }
#hp-bar { position: absolute; bottom: 30px; left: 30px; width: 280px; height: 28px; background: rgba(0,0,0,0.6); border: 2px solid #900; border-radius: 4px; overflow: hidden; }
#hp-fill { height: 100%; background: linear-gradient(90deg, #f00, #f80); width: 100%; transition: width 0.15s; }
#hp-text { position: absolute; bottom: 32px; left: 36px; font-size: 18px; font-weight: bold; text-shadow: 1px 1px 2px #000; }
#ammo { position: absolute; bottom: 30px; right: 30px; text-align: right; text-shadow: 1px 1px 3px #000; }
#ammo .weapon { font-size: 18px; color: #fa0; letter-spacing: 2px; }
#ammo .count { font-size: 48px; color: #fff; font-weight: bold; }
#ammo .count.low { color: #f00; }
#ammo .reloading { color: #fa0; font-size: 18px; }
#score-box { position: absolute; top: 30px; left: 30px; font-size: 20px; text-shadow: 1px 1px 3px #000; }
#score-box .wave { color: #f80; font-size: 28px; font-weight: bold; }
#score-box .score { color: #fff; }
#score-box .timer { color: #0ff; font-size: 24px; font-weight: bold; }
#crosshair { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 24px; height: 24px; }
#crosshair::before, #crosshair::after { content: ''; position: absolute; background: rgba(255,255,255,0.8); }
#crosshair::before { width: 2px; height: 24px; left: 11px; top: 0; }
#crosshair::after { width: 24px; height: 2px; left: 0; top: 11px; }
#damage-overlay { position: absolute; inset: 0; pointer-events: none; background: radial-gradient(circle, transparent 30%, rgba(200,0,0,0.7) 100%); opacity: 0; transition: opacity 0.15s; }
#damage-overlay.hit { opacity: 1; }
#lowhp-overlay { position: absolute; inset: 0; pointer-events: none; background: radial-gradient(circle, transparent 50%, rgba(150,0,0,0.5) 100%); opacity: 0; transition: opacity 0.5s; }
#lowhp-overlay.active { opacity: 1; }
#hit-marker { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 40px; height: 40px; opacity: 0; }
#hit-marker::before, #hit-marker::after { content: ''; position: absolute; background: #f00; transform-origin: center; }
#hit-marker::before { width: 2px; height: 40px; left: 19px; top: 0; transform: rotate(45deg); }
#hit-marker::after { width: 2px; height: 40px; left: 19px; top: 0; transform: rotate(-45deg); }
#minimap { position: absolute; top: 20px; right: 20px; width: 160px; height: 160px; background: rgba(0,0,0,0.6); border: 2px solid #555; border-radius: 4px; }

#pause { position: absolute; inset: 0; z-index: 50; background: rgba(0,0,0,0.85); display: none; flex-direction: column; justify-content: center; align-items: center; }
#pause.active { display: flex; }
#pause h2 { font-size: 56px; color: #c00; margin-bottom: 40px; letter-spacing: 4px; }
#pause button { width: 280px; padding: 16px; margin: 8px; font-size: 20px; font-family: inherit; font-weight: bold; background: transparent; color: #fff; border: 2px solid #c00; border-radius: 4px; cursor: pointer; transition: all 0.2s; letter-spacing: 2px; }
#pause button:hover { background: #c00; color: #000; }

#gameover { position: absolute; inset: 0; z-index: 60; background: rgba(0,0,0,0.92); display: none; flex-direction: column; justify-content: center; align-items: center; }
#gameover.active { display: flex; }
#gameover h1 { font-size: 64px; color: #c00; margin-bottom: 16px; letter-spacing: 4px; }
#gameover .stats { color: #ccc; font-size: 20px; margin: 4px 0; }
#gameover .stats span { color: #fff; font-weight: bold; }
#gameover .scores { margin-top: 20px; color: #f80; font-size: 16px; }
#gameover .scores div { margin: 2px 0; }
#gameover button { margin-top: 24px; width: 280px; padding: 14px; font-size: 18px; font-family: inherit; font-weight: bold; background: #c00; color: #000; border: none; border-radius: 4px; cursor: pointer; letter-spacing: 2px; }
#gameover button:hover { background: #f00; }

#loading { position: absolute; inset: 0; z-index: 200; background: #000; display: flex; justify-content: center; align-items: center; font-size: 24px; color: #c00; letter-spacing: 4px; }
#loading.hidden { display: none; }
</style>
</head>
<body>

<div id="loading">ЗАГРУЗКА...</div>

<div id="menu" style="display:none">
  <h1>ZOMBIE SURVIVAL</h1>
  <div class="subtitle">ВЫЖИВИ КАК МОЖНО ДОЛЬШЕ</div>
  <div class="section-title">ВЫБЕРИ РЕЖИМ</div>
  <div id="mode-buttons">
    <button id="btn-waves">ВОЛНЫ ЗОМБИ</button>
    <button id="btn-timed">ВЫЖИВАНИЕ 5 МИНУТ</button>
    <button id="btn-walk">ПРОГУЛКА (без зомби)</button>
  </div>
  <button id="btn-settings">НАСТРОЙКИ</button>
</div>

<div id="settings">
  <h2>НАСТРОЙКИ</h2>
  <div class="row"><label>Чувствительность мыши: <span class="val" id="sens-val">2.0</span></label><input type="range" id="sens" min="0.5" max="6" step="0.1" value="2.0"></div>
  <div class="row"><label>Громкость: <span class="val" id="vol-val">50%</span></label><input type="range" id="vol" min="0" max="100" step="5" value="50"></div>
  <div class="row"><label>Тени: <span class="val" id="shadow-val">ВКЛ</span></label><input type="range" id="shadow" min="0" max="1" step="1" value="1"></div>
  <button id="btn-settings-back">НАЗАД</button>
</div>

<div id="hud">
  <div id="hp-bar"><div id="hp-fill"></div></div>
  <div id="hp-text">100</div>
  <div id="ammo"><div class="weapon" id="weapon-name">ПИСТОЛЕТ</div><div class="count" id="ammo-count">12</div><div class="reloading" id="reloading" style="display:none">ПЕРЕЗАРЯДКА...</div></div>
  <div id="score-box">
    <div class="wave" id="wave-line">ВОЛНА <span id="wave">1</span></div>
    <div class="score">СЧЁТ <span id="score">0</span></div>
    <div class="timer" id="timer-line" style="display:none">05:00</div>
  </div>
  <div id="crosshair"></div>
  <div id="hit-marker"></div>
  <div id="damage-overlay"></div>
  <div id="lowhp-overlay"></div>
  <canvas id="minimap" width="160" height="160"></canvas>
</div>

<div id="pause"><h2>ПАУЗА</h2><button id="btn-resume">ПРОДОЛЖИТЬ</button><button id="btn-menu">В МЕНЮ</button></div>

<div id="gameover">
  <h1>ВЫ ПОГИБЛИ</h1>
  <div class="stats" id="go-mode">Режим: Волны</div>
  <div class="stats">Волна: <span id="go-wave">1</span></div>
  <div class="stats">Счёт: <span id="go-score">0</span></div>
  <div class="stats">Убито зомби: <span id="go-kills">0</span></div>
  <div class="scores" id="go-scores"></div>
  <button id="btn-restart">ИГРАТЬ СНОВА</button>
  <button id="btn-go-menu" style="background:transparent;color:#fff;border:2px solid #c00;margin-top:8px">В МЕНЮ</button>
</div>

<script type="importmap">
{ "imports": { "three": "https://unpkg.com/three@0.160.0/build/three.module.js" } }
</script>
<script type="module">
import * as THREE from 'three';

const CONFIG = {
  playerSpeed: 5.5, playerRunSpeed: 9, playerHeight: 1.7,
  mouseSensitivity: 0.002, arenaSize: 70, maxZombies: 14,
  waveBaseZombies: 3, waveZombiesPerWave: 2,
  zombieBaseSpeed: 1.8, zombieBaseHealth: 60,
  zombieDamage: 12, zombieAttackRange: 1.6, zombieAttackCooldown: 1000,
  timedModeDuration: 300, bossEveryWaves: 5,
};

const WEAPONS = {
  pistol:  { name: 'ПИСТОЛЕТ',  damage: 34,  fireRate: 280,  magSize: 12, reloadTime: 1400, spread: 0.008, range: 80, color: 0x222222 },
  rifle:   { name: 'АВТОМАТ',   damage: 22,  fireRate: 95,   magSize: 30, reloadTime: 2000, spread: 0.03,  range: 70, color: 0x333322 },
  shotgun: { name: 'ДРОБОВИК',  damage: 14,  fireRate: 750,  magSize: 6,  reloadTime: 2600, spread: 0.15,  range: 25, color: 0x442211, pellets: 8 },
  sniper:  { name: 'СНАЙПЕРКА', damage: 150, fireRate: 1500, magSize: 5,  reloadTime: 3000, spread: 0.001, range: 150, color: 0x111111 },
};
const WEAPON_ORDER = ['pistol','rifle','shotgun','sniper'];
const MELEE = { knife: { name: 'НОЖ', damage: 90, fireRate: 500, range: 2.2 } };

const settings = { sensitivity: 2.0, volume: 0.5, shadows: true };
function loadSettings() {
  try { Object.assign(settings, JSON.parse(localStorage.getItem('zs_settings') || '{}')); } catch(e) {}
  document.getElementById('sens').value = settings.sensitivity;
  document.getElementById('sens-val').textContent = settings.sensitivity.toFixed(1);
  document.getElementById('vol').value = Math.round(settings.volume*100);
  document.getElementById('vol-val').textContent = Math.round(settings.volume*100) + '%';
  document.getElementById('shadow').value = settings.shadows ? 1 : 0;
  document.getElementById('shadow-val').textContent = settings.shadows ? 'ВКЛ' : 'ВЫКЛ';
  CONFIG.mouseSensitivity = 0.001 * settings.sensitivity;
}
function saveSettings() { localStorage.setItem('zs_settings', JSON.stringify(settings)); }

let audioCtx = null;
function initAudio() {
  if (audioCtx) return;
  try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
}
function playSound(freq, duration, type='square', vol=0.3) {
  if (!audioCtx || settings.volume <= 0) return;
  try {
    const o = audioCtx.createOscillator(); const g = audioCtx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, audioCtx.currentTime);
    o.frequency.exponentialRampToValueAtTime(freq*0.5, audioCtx.currentTime + duration);
    g.gain.setValueAtTime(vol * settings.volume, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
    o.connect(g); g.connect(audioCtx.destination);
    o.start(); o.stop(audioCtx.currentTime + duration);
  } catch(e) {}
}
function soundShot() { playSound(200, 0.08, 'square', 0.4); playSound(100, 0.12, 'sawtooth', 0.2); }
function soundReload() { playSound(400, 0.1, 'sine', 0.2); setTimeout(() => playSound(600, 0.1, 'sine', 0.2), 150); }
function soundHit() { playSound(800, 0.05, 'sine', 0.3); }
function soundZombie() { playSound(80, 0.3, 'sawtooth', 0.15); }
function soundHurt() { playSound(150, 0.2, 'square', 0.3); }
function soundEmpty() { playSound(300, 0.05, 'square', 0.2); }

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a12);
scene.fog = new THREE.Fog(0x0a0a12, 20, 90);

const camera = new THREE.PerspectiveCamera(75, innerWidth/innerHeight, 0.1, 300);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
renderer.domElement.tabIndex = 0;

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

scene.add(new THREE.AmbientLight(0x404060, 0.6));
const moon = new THREE.DirectionalLight(0x8899ff, 0.4);
moon.position.set(30, 50, 20); moon.castShadow = true;
moon.shadow.mapSize.set(2048, 2048);
const sc = moon.shadow.camera; sc.left=-60; sc.right=60; sc.top=60; sc.bottom=-60;
scene.add(moon);

for (const [x,z] of [[-20,-20],[20,-20],[-20,20],[20,20],[0,0]]) {
  const lamp = new THREE.PointLight(0xffaa55, 1.2, 25);
  lamp.position.set(x, 6, z); lamp.castShadow = true; scene.add(lamp);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 6), new THREE.MeshStandardMaterial({ color: 0x333333 }));
  pole.position.set(x, 3, z); pole.castShadow = true; scene.add(pole);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.3, 8, 8), new THREE.MeshBasicMaterial({ color: 0xffaa55 }));
  bulb.position.set(x, 6, z); scene.add(bulb);
}

function makeFloorTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#3a3a3a'; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 3000; i++) { const g = 30 + Math.random()*40; ctx.fillStyle = `rgb(${g},${g},${g})`; ctx.fillRect(Math.random()*256, Math.random()*256, 2, 2); }
  ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1;
  for (let i = 0; i < 8; i++) { ctx.beginPath(); let x = Math.random()*256, y = Math.random()*256; ctx.moveTo(x, y); for (let j = 0; j < 5; j++) { x += (Math.random()-0.5)*40; y += (Math.random()-0.5)*40; ctx.lineTo(x, y); } ctx.stroke(); }
  ctx.strokeStyle = 'rgba(0,0,0,0.3)'; ctx.lineWidth = 2; ctx.strokeRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c); tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.repeat.set(10, 10); return tex;
}
function makeWallTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#4a4a3a'; ctx.fillRect(0, 0, 256, 256);
  const bw = 64, bh = 32;
  for (let y = 0; y < 256; y += bh) {
    const offset = (y/bh)%2 === 0 ? 0 : bw/2;
    for (let x = -bw; x < 256; x += bw) { const g = 50+Math.random()*30; ctx.fillStyle = `rgb(${g+20},${g+10},${g-10})`; ctx.fillRect(x+offset+2, y+2, bw-4, bh-4); }
  }
  const tex = new THREE.CanvasTexture(c); tex.wrapS = tex.wrapT = THREE.RepeatWrapping; return tex;
}
function makeZombieTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#3a5a2a'; ctx.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 40; i++) { ctx.fillStyle = `rgba(${20+Math.random()*30},${40+Math.random()*40},${20+Math.random()*20},0.7)`; ctx.beginPath(); ctx.arc(Math.random()*128, Math.random()*128, 2+Math.random()*6, 0, Math.PI*2); ctx.fill(); }
  ctx.fillStyle = 'rgba(100,0,0,0.6)';
  for (let i = 0; i < 10; i++) { ctx.beginPath(); ctx.arc(Math.random()*128, Math.random()*128, 3+Math.random()*8, 0, Math.PI*2); ctx.fill(); }
  return new THREE.CanvasTexture(c);
}
const floorTex = makeFloorTexture();
const wallTex = makeWallTexture();
const zombieTex = makeZombieTexture();

const half = CONFIG.arenaSize / 2;
const floor = new THREE.Mesh(new THREE.PlaneGeometry(CONFIG.arenaSize, CONFIG.arenaSize), new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.95 }));
floor.rotation.x = -Math.PI/2; floor.receiveShadow = true; scene.add(floor);

const colliders = [];
const wallMatBase = new THREE.MeshStandardMaterial({ map: wallTex, roughness: 0.9 });
function addWall(x, z, w, d, h=5) {
  const mat = wallMatBase.clone();
  mat.map = wallTex.clone(); mat.map.wrapS = mat.map.wrapT = THREE.RepeatWrapping;
  mat.map.repeat.set(Math.max(1, w/4), Math.max(1, h/4)); mat.map.needsUpdate = true;
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, h/2, z); m.castShadow = true; m.receiveShadow = true; scene.add(m);
  colliders.push({ x, z, halfW: w/2, halfD: d/2, h });
}
addWall(0, -half, CONFIG.arenaSize, 1.5);
addWall(0, half, CONFIG.arenaSize, 1.5);
addWall(-half, 0, 1.5, CONFIG.arenaSize);
addWall(half, 0, 1.5, CONFIG.arenaSize);
const layout = [
  [-18,-18,10,2],[18,-18,10,2],[-18,18,10,2],[18,18,10,2],
  [0,-14,2,10],[0,14,2,10],[-14,0,10,2],[14,0,10,2],
  [-8,-8,3,3],[8,8,3,3],[-8,8,3,3],[8,-8,3,3],
  [-25,0,2,14],[25,0,2,14],[0,0,4,4],
];
for (const [x,z,w,d] of layout) addWall(x, z, w, d, 3 + Math.random()*2);

function blockedStatic(x, z, r) {
  for (const c of colliders) {
    if (Math.abs(x-c.x) < c.halfW+r && Math.abs(z-c.z) < c.halfD+r) return true;
  }
  return false;
}

const player = {
  pos: new THREE.Vector3(0, CONFIG.playerHeight, 0),
  yaw: 0, pitch: 0, health: 100, maxHealth: 100,
  weapon: 'pistol', ammo: { pistol: 12, rifle: 30, shotgun: 6, sniper: 5 },
  reloading: false, lastShot: 0, lastMelee: 0,
};

const weaponModels = {};
function makeWeaponModel(name) {
  const g = new THREE.Group(); const w = WEAPONS[name];
  const body = new THREE.Mesh(new THREE.BoxGeometry(name==='sniper'?0.1:0.12, name==='sniper'?0.12:0.16, name==='sniper'?0.55:0.4), new THREE.MeshStandardMaterial({ color: w.color, metalness: 0.7, roughness: 0.4 }));
  body.position.set(0.25, -0.25, -0.45); g.add(body);
  const barrel = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, name==='sniper'?0.7:0.45), new THREE.MeshStandardMaterial({ color: 0x111111, metalness: 0.8, roughness: 0.3 }));
  barrel.position.set(0.25, -0.21, -0.75); g.add(barrel);
  if (name === 'rifle' || name === 'sniper') {
    const scope = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.2, 8), new THREE.MeshStandardMaterial({ color: 0x111111 }));
    scope.rotation.x = Math.PI/2; scope.position.set(0.25, -0.14, -0.5); g.add(scope);
  }
  return g;
}
for (const w of WEAPON_ORDER) { const m = makeWeaponModel(w); m.visible = (w === 'pistol'); weaponModels[w] = m; camera.add(m); }

const knifeGroup = new THREE.Group();
const blade = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.04, 0.35), new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.9, roughness: 0.2 }));
blade.position.set(0.3, -0.3, -0.5); knifeGroup.add(blade);
const handle = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.1, 0.15), new THREE.MeshStandardMaterial({ color: 0x442211, roughness: 0.9 }));
handle.position.set(0.3, -0.32, -0.3); knifeGroup.add(handle);
knifeGroup.visible = false; camera.add(knifeGroup);
scene.add(camera);

// ============ ВВОД (ФИКС: фокус на body и canvas) ============
const keys = {};
function forceFocus() {
  try { document.body.focus(); } catch(e) {}
  try { renderer.domElement.focus(); } catch(e) {}
}

addEventListener('keydown', e => {
  if (['KeyW','KeyA','KeyS','KeyD','Space','ShiftLeft','ShiftRight','KeyR','KeyV','Escape'].includes(e.code)) e.preventDefault();
  keys[e.code] = true;
  if (e.code === 'KeyR') reload();
  if (e.code === 'Digit1') switchWeapon('pistol');
  if (e.code === 'Digit2') switchWeapon('rifle');
  if (e.code === 'Digit3') switchWeapon('shotgun');
  if (e.code === 'Digit4') switchWeapon('sniper');
  if (e.code === 'KeyV') meleeAttack();
  if (e.code === 'Escape' && state.running) pauseGame();
});
addEventListener('keyup', e => keys[e.code] = false);
addEventListener('blur', () => { for (const k in keys) keys[k] = false; });

let mouseDown = false;
addEventListener('mousedown', e => {
  forceFocus();
  if (e.button === 0 && document.pointerLockElement === renderer.domElement) {
    mouseDown = true;
    if (player.weapon === 'knife') meleeAttack(); else shoot();
  }
  if (e.button === 2 && player.weapon === 'sniper') { camera.fov = 25; camera.updateProjectionMatrix(); }
});
addEventListener('mouseup', e => {
  if (e.button === 0) mouseDown = false;
  if (e.button === 2) { camera.fov = 75; camera.updateProjectionMatrix(); }
});
addEventListener('contextmenu', e => e.preventDefault());

addEventListener('wheel', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  let idx = WEAPON_ORDER.indexOf(player.weapon);
  if (idx < 0) idx = 0;
  const next = (idx + (e.deltaY > 0 ? 1 : -1) + WEAPON_ORDER.length) % WEAPON_ORDER.length;
  switchWeapon(WEAPON_ORDER[next]);
});

addEventListener('mousemove', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  player.yaw -= e.movementX * CONFIG.mouseSensitivity;
  player.pitch -= e.movementY * CONFIG.mouseSensitivity;
  player.pitch = Math.max(-Math.PI/2+0.01, Math.min(Math.PI/2-0.01, player.pitch));
});

const raycaster = new THREE.Raycaster();
const screenCenter = new THREE.Vector2(0, 0);

function switchWeapon(w) {
  if (player.reloading) return;
  player.weapon = w;
  for (const k of WEAPON_ORDER) weaponModels[k].visible = (k === w);
  knifeGroup.visible = (w === 'knife');
  updateHUD();
}

function shoot() {
  const w = WEAPONS[player.weapon];
  if (!w) return;
  if (player.reloading) return;
  if (player.ammo[player.weapon] <= 0) { reload(); soundEmpty(); return; }
  const now = performance.now();
  if (now - player.lastShot < w.fireRate) return;
  player.lastShot = now;
  player.ammo[player.weapon]--;
  updateHUD(); soundShot(); spawnShell(); spawnMuzzleFlash();

  const pellets = w.pellets || 1;
  for (let i = 0; i < pellets; i++) {
    raycaster.setFromCamera(screenCenter, camera);
    if (w.spread > 0) {
      const dir = raycaster.ray.direction.clone();
      dir.x += (Math.random()-0.5)*w.spread; dir.y += (Math.random()-0.5)*w.spread; dir.z += (Math.random()-0.5)*w.spread;
      dir.normalize(); raycaster.ray.direction.copy(dir);
    }
    raycaster.far = w.range;
    const targets = zombies.filter(z => z.alive).map(z => z.mesh);
    const hits = raycaster.intersectObjects(targets, true);
    if (hits.length) {
      const hit = hits[0];
      let zombie = null;
      for (const z of zombies) { if (z.alive && (z.mesh === hit.object || z.mesh.children.includes(hit.object))) { zombie = z; break; } }
      if (zombie) {
        zombie.health -= w.damage;
        spawnBlood(hit.point, 12); showHitMarker(); soundHit();
        if (zombie.health <= 0) killZombie(zombie);
      }
    } else {
      const worldHits = raycaster.intersectObjects(scene.children, true);
      if (worldHits.length) spawnParticles(worldHits[0].point, 0x999999, 3);
    }
  }
  const model = weaponModels[player.weapon];
  if (model) model.position.z = 0.06;
}

function reload() {
  const w = WEAPONS[player.weapon];
  if (!w) return;
  if (player.reloading || player.ammo[player.weapon] >= w.magSize) return;
  player.reloading = true; updateHUD(); soundReload();
  setTimeout(() => { player.ammo[player.weapon] = w.magSize; player.reloading = false; updateHUD(); }, w.reloadTime);
}

function meleeAttack() {
  const now = performance.now();
  if (now - player.lastMelee < MELEE.knife.fireRate) return;
  player.lastMelee = now;
  knifeGroup.position.z = -0.15;
  setTimeout(() => { knifeGroup.position.z = 0; }, 100);
  soundShot();
  const forward = new THREE.Vector3(-Math.sin(player.yaw), 0, -Math.cos(player.yaw));
  for (const z of zombies) {
    if (!z.alive) continue;
    const toZombie = new THREE.Vector3().subVectors(z.mesh.position, player.pos).setY(0);
    const dist = toZombie.length();
    if (dist < MELEE.knife.range) {
      const angle = forward.angleTo(toZombie);
      if (angle < Math.PI/3) {
        z.health -= MELEE.knife.damage;
        spawnBlood(z.mesh.position.clone().setY(1), 18); showHitMarker(); soundHit();
        if (z.health <= 0) killZombie(z);
      }
    }
  }
}

const shells = [];
const shellGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.06, 6);
const shellMat = new THREE.MeshStandardMaterial({ color: 0xccaa33, metalness: 0.9, roughness: 0.3 });
function spawnShell() {
  const m = new THREE.Mesh(shellGeo, shellMat); m.position.copy(camera.position);
  m.position.x += 0.2; m.position.y -= 0.2; scene.add(m);
  shells.push({ mesh: m, vel: new THREE.Vector3((Math.random()-0.5)*2, Math.random()*2+1, (Math.random()-0.5)*2), life: 2 });
}
function spawnMuzzleFlash() {
  const flash = new THREE.PointLight(0xffaa00, 2, 5);
  flash.position.copy(camera.position);
  const dir = new THREE.Vector3(0,0,-1).applyQuaternion(camera.quaternion);
  flash.position.addScaledVector(dir, 0.5); scene.add(flash);
  setTimeout(() => scene.remove(flash), 50);
}
const bloodParticles = [];
const bloodGeo = new THREE.SphereGeometry(0.06, 4, 4);
function spawnBlood(pos, count) {
  for (let i = 0; i < count; i++) {
    const m = new THREE.Mesh(bloodGeo, new THREE.MeshBasicMaterial({ color: 0xaa0000 }));
    m.position.copy(pos); scene.add(m);
    bloodParticles.push({ mesh: m, vel: new THREE.Vector3((Math.random()-0.5)*7, Math.random()*4+1, (Math.random()-0.5)*7), life: 0.6 + Math.random()*0.4 });
  }
}
function spawnParticles(pos, color, count) {
  for (let i = 0; i < count; i++) {
    const m = new THREE.Mesh(bloodGeo, new THREE.MeshBasicMaterial({ color }));
    m.position.copy(pos); scene.add(m);
    bloodParticles.push({ mesh: m, vel: new THREE.Vector3((Math.random()-0.5)*7, Math.random()*4+1, (Math.random()-0.5)*7), life: 0.5 + Math.random()*0.3 });
  }
}

const zombies = [];
const ZOMBIE_TYPES = {
  normal: { color: 0x6a8a4a, healthMult: 1.0, speedMult: 1.0, damage: 12, scale: 1.0, score: 50 },
  rusher: { color: 0xff6644, healthMult: 0.5, speedMult: 2.2, damage: 8,  scale: 0.85, score: 75 },
  tank:   { color: 0x884444, healthMult: 3.5, speedMult: 0.6, damage: 25, scale: 1.5, score: 150 },
  boss:   { color: 0xaa00aa, healthMult: 15.0, speedMult: 0.7, damage: 40, scale: 2.2, score: 500 },
};

function spawnZombie(typeKey='normal') {
  const t = ZOMBIE_TYPES[typeKey];
  let x, z, tries = 0;
  do {
    x = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    z = (Math.random()-0.5)*(CONFIG.arenaSize-8);
    tries++;
  } while ((Math.hypot(x-player.pos.x, z-player.pos.z) < 18 || blockedStatic(x, z, 2.5)) && tries < 200);

  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.7*t.scale, 1.4*t.scale, 0.5*t.scale), new THREE.MeshStandardMaterial({ map: zombieTex.clone(), color: t.color, roughness: 0.9 }));
  body.position.y = 0.7*t.scale; body.castShadow = true; group.add(body);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.5*t.scale, 0.5*t.scale, 0.5*t.scale), new THREE.MeshStandardMaterial({ color: t.color, roughness: 0.9 }));
  head.position.y = 1.55*t.scale; head.castShadow = true; group.add(head);
  const eyeMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
  const eyeL = new THREE.Mesh(new THREE.SphereGeometry(0.06*t.scale, 6, 6), eyeMat);
  eyeL.position.set(-0.12*t.scale, 1.6*t.scale, 0.26*t.scale); group.add(eyeL);
  const eyeR = new THREE.Mesh(new THREE.SphereGeometry(0.06*t.scale, 6, 6), eyeMat);
  eyeR.position.set(0.12*t.scale, 1.6*t.scale, 0.26*t.scale); group.add(eyeR);
  group.position.set(x, 0, z); scene.add(group);

  const waveMult = 1 + (wave-1)*0.12;
  zombies.push({
    type: typeKey, mesh: group,
    health: CONFIG.zombieBaseHealth * t.healthMult * waveMult,
    maxHealth: CONFIG.zombieBaseHealth * t.healthMult * waveMult,
    speed: CONFIG.zombieBaseSpeed * t.speedMult * (1 + (wave-1)*0.05),
    damage: t.damage, score: t.score,
    lastAttack: 0, alive: true,
    stuckCounter: 0,
  });
}

function killZombie(z) {
  z.alive = false; scene.remove(z.mesh);
  score += z.score; kills++; updateHUD();
  spawnBlood(z.mesh.position.clone().setY(1), 30); soundZombie();
}

let score = 0, kills = 0, wave = 1;
let zombiesToSpawn = 0;
let waveActive = false;
let waveDelayTimer = 0;
let timedModeTimeLeft = 0;

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
const lowhpOverlay = document.getElementById('lowhp-overlay');
const timerLine = document.getElementById('timer-line');
const waveLine = document.getElementById('wave-line');
const minimapCanvas = document.getElementById('minimap');
const mmCtx = minimapCanvas.getContext('2d');

function updateHUD() {
  hpFill.style.width = Math.max(0, player.health) + '%';
  hpText.textContent = Math.max(0, Math.round(player.health));
  lowhpOverlay.classList.toggle('active', player.health < 30);
  const w = WEAPONS[player.weapon];
  if (w) {
    ammoCount.textContent = player.reloading ? '...' : player.ammo[player.weapon];
    ammoCount.classList.toggle('low', player.ammo[player.weapon] <= Math.max(3, w.magSize*0.25));
    weaponName.textContent = w.name;
    reloadingEl.style.display = player.reloading ? 'block' : 'none';
  } else {
    ammoCount.textContent = '∞'; ammoCount.classList.remove('low');
    weaponName.textContent = MELEE.knife.name; reloadingEl.style.display = 'none';
  }
  waveEl.textContent = wave;
  scoreEl.textContent = score;
}

function showHitMarker() { hitMarker.style.opacity = '1'; setTimeout(() => hitMarker.style.opacity = '0', 120); }
function flashDamage() { damageOverlay.classList.add('hit'); setTimeout(() => damageOverlay.classList.remove('hit'), 200); }

function drawMinimap() {
  const W = 160, H = 160;
  mmCtx.clearRect(0, 0, W, H);
  mmCtx.fillStyle = 'rgba(0,0,0,0.6)'; mmCtx.fillRect(0, 0, W, H);
  const scale = W / CONFIG.arenaSize;
  const toMM = (x, z) => [W/2 + x*scale, H/2 + z*scale];
  mmCtx.fillStyle = '#555';
  for (const c of colliders) { const [sx, sz] = toMM(c.x - c.halfW, c.z - c.halfD); mmCtx.fillRect(sx, sz, c.halfW*2*scale, c.halfD*2*scale); }
  for (const z of zombies) {
    if (!z.alive) continue;
    const [zx, zz] = toMM(z.mesh.position.x, z.mesh.position.z);
    mmCtx.fillStyle = z.type === 'boss' ? '#f0f' : z.type === 'rusher' ? '#f80' : z.type === 'tank' ? '#a44' : '#f00';
    mmCtx.beginPath(); mmCtx.arc(zx, zz, z.type === 'boss' ? 4 : 2.5, 0, Math.PI*2); mmCtx.fill();
  }
  const [px, pz] = toMM(player.pos.x, player.pos.z);
  mmCtx.fillStyle = '#0f0'; mmCtx.beginPath(); mmCtx.arc(px, pz, 3, 0, Math.PI*2); mmCtx.fill();
  mmCtx.strokeStyle = '#0f0'; mmCtx.lineWidth = 2;
  mmCtx.beginPath(); mmCtx.moveTo(px, pz); mmCtx.lineTo(px - Math.sin(player.yaw)*8, pz - Math.cos(player.yaw)*8); mmCtx.stroke();
}

const state = { running: false, paused: false, mode: 'waves' };
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
    const nx = player.pos.x + move.x; const nz = player.pos.z + move.z;
    if (!blockedStatic(nx, player.pos.z, 0.5) && Math.abs(nx) < half-1.5) player.pos.x = nx;
    if (!blockedStatic(player.pos.x, nz, 0.5) && Math.abs(nz) < half-1.5) player.pos.z = nz;
  }

  camera.position.copy(player.pos);
  camera.rotation.order = 'YXZ';
  camera.rotation.y = player.yaw; camera.rotation.x = player.pitch;

  for (const k of WEAPON_ORDER) { const m = weaponModels[k]; m.position.z += (0 - m.position.z) * dt * 12; }
  knifeGroup.position.z += (0 - knifeGroup.position.z) * dt * 12;

  if (mouseDown && player.weapon !== 'knife') shoot();

  if (state.mode === 'waves') {
    if (!waveActive && zombiesToSpawn <= 0 && zombies.filter(z => z.alive).length === 0) {
      waveDelayTimer += dt;
      if (waveDelayTimer > 2) {
        wave++; zombiesToSpawn = CONFIG.waveBaseZombies + (wave-1)*CONFIG.waveZombiesPerWave;
        waveActive = true; waveDelayTimer = 0; updateHUD();
      }
    }
    if (waveActive && zombiesToSpawn > 0) {
      const spawnInterval = Math.max(0.3, 1.2 - wave*0.05);
      if (performance.now() - (state.lastSpawn || 0) > spawnInterval*1000) {
        state.lastSpawn = performance.now();
        const aliveCount = zombies.filter(z => z.alive).length;
        if (aliveCount < CONFIG.maxZombies) {
          let type = 'normal'; const r = Math.random();
          if (wave >= 2 && r < 0.25) type = 'rusher';
          if (wave >= 3 && r > 0.85) type = 'tank';
          if (wave % CONFIG.bossEveryWaves === 0 && zombiesToSpawn === 1) type = 'boss';
          spawnZombie(type); zombiesToSpawn--;
        }
      }
      if (zombiesToSpawn <= 0) waveActive = false;
    }
  }

  if (state.mode === 'timed') {
    timedModeTimeLeft -= dt;
    const m = Math.floor(timedModeTimeLeft / 60); const s = Math.floor(timedModeTimeLeft % 60);
    timerLine.textContent = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
    if (timedModeTimeLeft <= 0) { winGame(); return; }
    const aliveCount = zombies.filter(z => z.alive).length;
    const targetCount = 6 + Math.floor((CONFIG.timedModeDuration - timedModeTimeLeft) / 30);
    if (aliveCount < Math.min(targetCount, CONFIG.maxZombies) && performance.now() - (state.lastSpawn || 0) > 700) {
      state.lastSpawn = performance.now();
      let type = 'normal'; const r = Math.random();
      if (r < 0.3) type = 'rusher'; else if (r > 0.9) type = 'tank';
      spawnZombie(type);
    }
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
        // ФИКС: если зомби внутри коллайдера — выталкиваем к игроку напрямую
        if (blockedStatic(z.mesh.position.x, z.mesh.position.z, 0.5)) {
          z.mesh.position.x += dir.x * step * 1.5;
          z.mesh.position.z += dir.z * step * 1.5;
        } else {
          const nx = z.mesh.position.x + dir.x * step;
          const nz = z.mesh.position.z + dir.z * step;
          let moved = false;
          if (!blockedStatic(nx, z.mesh.position.z, 0.5)) { z.mesh.position.x = nx; moved = true; }
          if (!blockedStatic(z.mesh.position.x, nz, 0.5)) { z.mesh.position.z = nz; moved = true; }
          // ФИКС: если застрял (не сдвинулся) — обходим препятствие
          if (!moved) {
            z.stuckCounter = (z.stuckCounter || 0) + 1;
            if (z.stuckCounter > 5) {
              const perp = new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(step * 1.2);
              z.mesh.position.add(perp);
              z.stuckCounter = 0;
            }
          } else {
            z.stuckCounter = 0;
          }
        }
      }
      z.mesh.rotation.y = Math.atan2(dir.x, dir.z);
    }
    if (dist < CONFIG.zombieAttackRange && now - z.lastAttack > CONFIG.zombieAttackCooldown) {
      z.lastAttack = now;
      player.health -= z.damage;
      flashDamage(); soundHurt(); updateHUD();
      if (player.health <= 0) { player.health = 0; gameOver(); }
    }
  }

  for (let i = shells.length-1; i >= 0; i--) {
    const s = shells[i];
    s.vel.y -= 15*dt; s.mesh.position.addScaledVector(s.vel, dt); s.mesh.rotation.x += dt*10; s.life -= dt;
    if (s.life <= 0 || s.mesh.position.y < 0.05) { scene.remove(s.mesh); shells.splice(i, 1); }
  }
  for (let i = bloodParticles.length-1; i >= 0; i--) {
    const p = bloodParticles[i];
    p.vel.y -= 12*dt; p.mesh.position.addScaledVector(p.vel, dt); p.life -= dt;
    if (p.life <= 0) { scene.remove(p.mesh); bloodParticles.splice(i, 1); }
  }

  drawMinimap();
}

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const dt = Math.min((now - lastTime)/1000, 0.05);
  lastTime = now;
  update(dt);
  renderer.render(scene, camera);
}

const menuEl = document.getElementById('menu');
const pauseEl = document.getElementById('pause');
const gameoverEl = document.getElementById('gameover');
const settingsEl = document.getElementById('settings');
const loadingEl = document.getElementById('loading');

function resetGame(mode) {
  player.pos.set(0, CONFIG.playerHeight, 0);
  player.yaw = 0; player.pitch = 0;
  player.health = player.maxHealth;
  player.ammo = { pistol: 12, rifle: 30, shotgun: 6, sniper: 5 };
  player.weapon = 'pistol'; player.reloading = false;
  for (const k of WEAPON_ORDER) weaponModels[k].visible = (k === 'pistol');
  knifeGroup.visible = false;
  score = 0; kills = 0; wave = 1;
  zombiesToSpawn = CONFIG.waveBaseZombies;
  waveActive = (mode === 'waves');
  waveDelayTimer = 0;
  timedModeTimeLeft = CONFIG.timedModeDuration;
  state.running = true; state.paused = false; state.mode = mode;
  state.lastSpawn = 0;

  for (const z of zombies) if (z.alive) scene.remove(z.mesh);
  zombies.length = 0;
  for (const p of bloodParticles) scene.remove(p.mesh);
  bloodParticles.length = 0;
  for (const s of shells) scene.remove(s.mesh);
  shells.length = 0;

  timerLine.style.display = (mode === 'timed') ? 'block' : 'none';
  waveLine.style.display = (mode === 'walk') ? 'none' : 'block';

  menuEl.style.display = 'none';
  pauseEl.classList.remove('active');
  gameoverEl.classList.remove('active');
  settingsEl.classList.remove('active');
  hudEl.classList.add('active');

  updateHUD();
  forceFocus();
  renderer.domElement.requestPointerLock();
  lastTime = performance.now();
  initAudio();
}

function startWaves() { resetGame('waves'); }
function startTimed() { resetGame('timed'); }
function startWalk() { resetGame('walk'); }

function pauseGame() {
  if (!state.running || state.paused) return;
  state.paused = true; document.exitPointerLock(); pauseEl.classList.add('active');
}
function resumeGame() {
  state.paused = false; pauseEl.classList.remove('active');
  forceFocus(); renderer.domElement.requestPointerLock(); lastTime = performance.now();
}
function gameOver() {
  state.running = false; document.exitPointerLock();
  document.getElementById('go-mode').textContent = 'Режим: ' + (state.mode === 'waves' ? 'Волны' : state.mode === 'timed' ? '5 минут' : 'Прогулка');
  document.getElementById('go-wave').textContent = wave;
  document.getElementById('go-score').textContent = score;
  document.getElementById('go-kills').textContent = kills;
  gameoverEl.classList.add('active'); hudEl.classList.remove('active');
  submitScore(score); loadTopScores();
}
function winGame() {
  state.running = false; document.exitPointerLock();
  document.querySelector('#gameover h1').textContent = 'ПОБЕДА!';
  document.getElementById('go-mode').textContent = 'Режим: 5 минут';
  document.getElementById('go-wave').textContent = wave;
  document.getElementById('go-score').textContent = score;
  document.getElementById('go-kills').textContent = kills;
  gameoverEl.classList.add('active'); hudEl.classList.remove('active');
  submitScore(score); loadTopScores();
}
function backToMenu() {
  state.running = false; state.paused = false; document.exitPointerLock();
  hudEl.classList.remove('active'); pauseEl.classList.remove('active'); gameoverEl.classList.remove('active');
  document.querySelector('#gameover h1').textContent = 'ВЫ ПОГИБЛИ';
  menuEl.style.display = 'flex';
}

async function submitScore(s) {
  if (s <= 0) return;
  try { await fetch('/api/scores', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Player', score: s }) }); } catch(e) {}
}
async function loadTopScores() {
  try {
    const r = await fetch('/api/scores'); const data = await r.json();
    const box = document.getElementById('go-scores');
    if (!data.scores || !data.scores.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<div style="color:#888;margin-bottom:6px">ТОП-5:</div>' + data.scores.slice(0,5).map((s,i) => `<div>${i+1}. ${s.name} — ${s.score}</div>`).join('');
  } catch(e) {}
}

document.getElementById('btn-waves').addEventListener('click', startWaves);
document.getElementById('btn-timed').addEventListener('click', startTimed);
document.getElementById('btn-walk').addEventListener('click', startWalk);
document.getElementById('btn-settings').addEventListener('click', () => settingsEl.classList.add('active'));
document.getElementById('btn-settings-back').addEventListener('click', () => { settingsEl.classList.remove('active'); saveSettings(); });
document.getElementById('btn-resume').addEventListener('click', resumeGame);
document.getElementById('btn-menu').addEventListener('click', backToMenu);
document.getElementById('btn-restart').addEventListener('click', () => { document.querySelector('#gameover h1').textContent = 'ВЫ ПОГИБЛИ'; resetGame(state.mode); });
document.getElementById('btn-go-menu').addEventListener('click', backToMenu);

document.getElementById('sens').addEventListener('input', e => { settings.sensitivity = parseFloat(e.target.value); document.getElementById('sens-val').textContent = settings.sensitivity.toFixed(1); CONFIG.mouseSensitivity = 0.001 * settings.sensitivity; });
document.getElementById('vol').addEventListener('input', e => { settings.volume = parseInt(e.target.value) / 100; document.getElementById('vol-val').textContent = e.target.value + '%'; });
document.getElementById('shadow').addEventListener('input', e => { settings.shadows = e.target.value === '1'; document.getElementById('shadow-val').textContent = settings.shadows ? 'ВКЛ' : 'ВЫКЛ'; renderer.shadowMap.enabled = settings.shadows; moon.castShadow = settings.shadows; });

document.addEventListener('pointerlockchange', () => {
  if (document.pointerLockElement !== renderer.domElement && state.running && !state.paused) pauseGame();
});

loadSettings();
loadingEl.classList.add('hidden');
menuEl.style.display = 'flex';
updateHUD();
animate();
</script>
</body>
</html>
"""

@app.route('/')
def index(): return Response(INDEX_HTML, mimetype='text/html')

@app.route('/health')
@json_endpoint
def health(): return {'status': 'ok', 'time': time.time()}

@app.route('/api/scores', methods=['GET'])
@json_endpoint
def get_scores():
    scores = load_scores(); scores.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'count': len(scores), 'scores': scores[:TOP_N]}

@app.route('/api/scores', methods=['POST'])
@require_json
@json_endpoint
def post_score():
    ip = request.remote_addr or 'unknown'
    if rate_limited(ip): return jsonify({'error': 'rate_limited'}), 429
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', 'Anonymous')).strip()[:MAX_NAME_LEN] or 'Anonymous'
    try: score = int(data.get('score', 0))
    except (TypeError, ValueError): return jsonify({'error': 'invalid_score'}), 400
    if score < 0 or score > 10_000_000: return jsonify({'error': 'score_out_of_range'}), 400
    with file_lock:
        scores = load_scores()
        scores.append({'name': name, 'score': score, 'date': time.strftime('%Y-%m-%d %H:%M:%S')})
        scores.sort(key=lambda x: x.get('score', 0), reverse=True)
        scores = scores[:MAX_SCORES]; save_scores(scores)
    rank = next((i+1 for i,s in enumerate(scores) if s['score']==score and s['name']==name), None)
    return {'ok': True, 'rank': rank}

@app.errorhandler(404)
def not_found(e): return Response(INDEX_HTML, mimetype='text/html')

if __name__ == '__main__':
    log.info(f'Запуск на порту {PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG, threaded=True)
