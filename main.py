"""
GUNKEEPERS 3D — top-down 3D оборона склада на Three.js.
Часть 1: сервер + HTML/CSS + меню/HUD/магазин.
Часть 2: весь JavaScript (Three.js) — вставляется в конец INDEX_HTML.
Запуск: pip install flask && python main.py
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
log = logging.getLogger('gunkeeper3d')

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
        log.warning('Не удалось прочитать %s: %s', path, e)
        return default


def _save_json(path, data):
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log.error('Не удалось сохранить %s: %s', path, e)
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
            log.exception('Ошибка в %s: %s', fn.__name__, e)
            return jsonify({'error': 'internal_error', 'message': str(e)}), 500
    return wrapper


def require_json(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not request.is_json:
            return jsonify({'error': 'json_required'}), 400
        return fn(*a, **kw)
    return wrapper


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>GUNKEEPERS 3D — Ночная оборона</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:#07080b;color:#e9e2c8;font-family:"Courier New",Courier,monospace;overflow:hidden;user-select:none;-webkit-user-select:none;-webkit-tap-highlight-color:transparent;touch-action:none}
#wrap{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
canvas#game{display:block;background:#0b0d12;box-shadow:0 0 60px #000, 0 0 0 2px #1d2028}
.overlay{position:absolute;inset:0;z-index:20;display:none;align-items:center;justify-content:center;flex-direction:column;background:rgba(4,5,8,.88);backdrop-filter:blur(2px)}
.overlay.active{display:flex}
h1{font-size:56px;letter-spacing:6px;color:#d8b34a;text-shadow:0 0 24px #b8860b,0 0 60px #5a3a00}
h2{font-size:34px;letter-spacing:4px;color:#d8b34a;margin-bottom:14px}
.sub{color:#8a8f7a;letter-spacing:3px;margin:6px 0 26px;font-size:14px}
button{font-family:inherit;cursor:pointer;border:2px solid #6b5a24;background:#12140f;color:#e9e2c8;padding:12px 26px;font-size:17px;letter-spacing:2px;transition:.15s}
button:hover:not(:disabled){background:#d8b34a;color:#12140f;border-color:#d8b34a}
button:disabled{opacity:.35;cursor:not-allowed}
button.primary{border-color:#d8b34a;background:#241f10}
.col{display:flex;flex-direction:column;gap:10px;align-items:center}
.hint{color:#7c8172;font-size:13px;letter-spacing:1px;margin-top:18px;line-height:1.7;text-align:center}
.hint b{color:#d8b34a}
#hud{position:absolute;inset:0;pointer-events:none;z-index:10;display:none}
#hud.active{display:block}
.hbar{position:absolute;height:20px;background:rgba(0,0,0,.55);border:2px solid #3a3f2a;overflow:hidden}
.hbar i{display:block;height:100%;width:100%;transition:width .12s}
.hbar span{position:absolute;left:6px;top:1px;font-size:13px;font-weight:bold;text-shadow:1px 1px 2px #000}
#hpWrap{left:14px;top:12px;width:230px}
#hpFill{background:linear-gradient(90deg,#a33,#e55)}
#baseWrap{left:14px;top:38px;width:230px}
#baseFill{background:linear-gradient(90deg,#2a6,#5cf)}
#stat{position:absolute;right:14px;top:12px;text-align:right;font-size:15px;letter-spacing:1px;text-shadow:1px 1px 2px #000}
#stat .big{font-size:30px;color:#d8b34a;font-weight:bold}
#money{color:#8ee06a}
#banner{position:absolute;left:50%;top:34%;transform:translate(-50%,-50%);font-size:52px;letter-spacing:8px;color:#d84a3a;text-shadow:0 0 30px #000;opacity:0;transition:opacity .25s;white-space:nowrap}
#banner.show{opacity:1}
#ammoBox{position:absolute;right:14px;bottom:14px;text-align:right;text-shadow:1px 1px 3px #000}
#wName{color:#d8b34a;font-size:16px;letter-spacing:2px}
#aCount{font-size:34px;font-weight:bold}
#aCount.low{color:#e55}
#aRes{font-size:16px;color:#9a9f8a}
#reload{color:#e5a13a;font-size:15px;height:18px}
#slots{position:absolute;left:14px;bottom:14px;display:flex;gap:6px}
.slot{width:66px;padding:4px 2px;text-align:center;background:rgba(0,0,0,.55);border:2px solid #3a3f2a;font-size:11px;color:#8a8f7a}
.slot.on{border-color:#d8b34a;color:#e9e2c8;background:rgba(60,48,16,.6)}
.slot.lock{opacity:.3}
.slot b{display:block;font-size:13px}
#radar{position:absolute;right:14px;top:96px;width:132px;height:132px;border:2px solid #3a3f2a;background:rgba(0,0,0,.5)}
#shopBody{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0 18px;max-width:660px}
.shopItem{text-align:left;padding:10px 14px;font-size:14px;letter-spacing:0;line-height:1.5}
.shopItem b{display:block;color:#d8b34a;font-size:15px;letter-spacing:1px}
.shopItem small{color:#9a9f8a;font-size:12px}
#overStats{color:#c9c4ae;font-size:16px;line-height:1.9;text-align:center;margin-bottom:14px}
#overStats b{color:#e9e2c8}
input{font-family:inherit;font-size:16px;padding:8px 10px;background:#12140f;color:#e9e2c8;border:2px solid #6b5a24;width:200px;text-align:center;margin-bottom:12px}
#scores{margin-top:14px;color:#d8b34a;font-size:14px;text-align:center;line-height:1.7}
#vignette{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity .2s;background:radial-gradient(circle at 50% 50%,transparent 45%,rgba(150,10,10,.75) 100%)}
#flash{position:absolute;inset:0;pointer-events:none;opacity:0;background:#fff}
#loadTip{position:absolute;left:50%;bottom:40px;transform:translateX(-50%);color:#8a8f7a;font-size:13px;letter-spacing:2px}
</style>
</head>
<body>
<div id="wrap">
  <canvas id="game"></canvas>

  <div id="hud">
    <div class="hbar" id="hpWrap"><i id="hpFill"></i><span id="hpText">HP 100</span></div>
    <div class="hbar" id="baseWrap"><i id="baseFill"></i><span>СКЛАД</span></div>
    <div id="stat">
      <div class="big" id="waveTxt">ВОЛНА 1</div>
      <div id="money">$0</div>
      <div id="kills">☠ 0</div>
    </div>
    <canvas id="radar" width="132" height="132"></canvas>
    <div id="banner"></div>
    <div id="ammoBox">
      <div id="wName">РЕВОЛЬВЕР</div>
      <div id="aCount">6</div>
      <div id="aRes">∞</div>
      <div id="reload"></div>
    </div>
    <div id="slots"></div>
    <div id="vignette"></div>
    <div id="flash"></div>
  </div>

  <div class="overlay active" id="menu">
    <h1>GUNKEEPERS 3D</h1>
    <div class="sub">НОЧНАЯ ОБОРОНА СКЛАДА</div>
    <div class="col">
      <button class="primary" id="btnStart">НАЧАТЬ СМЕНУ</button>
      <button id="btnHelp">УПРАВЛЕНИЕ</button>
    </div>
    <div class="hint" id="helpText" style="display:none">
      <b>WASD / стрелки</b> — движение &nbsp;·&nbsp; <b>Shift</b> — бег<br>
      <b>Мышь</b> — прицел, <b>ЛКМ</b> — огонь (можно удерживать)<br>
      <b>1..5</b> — оружие, <b>колесо</b> — смена &nbsp;·&nbsp; <b>R</b> — перезарядка<br>
      <b>Esc</b> — пауза &nbsp;·&nbsp; зомби идут на склад, не дай им пройти!
    </div>
    <div id="loadTip">Загрузка 3D-сцены...</div>
  </div>

  <div class="overlay" id="shop">
    <h2 id="shopTitle">МАГАЗИН</h2>
    <div id="shopBody"></div>
    <button class="primary" id="btnNextWave">НАЧАТЬ ВОЛНУ</button>
    <div class="hint" id="shopMoney"></div>
  </div>

  <div class="overlay" id="pause">
    <h2>ПАУЗА</h2>
    <div class="col">
      <button class="primary" id="btnResume">ПРОДОЛЖИТЬ</button>
      <button id="btnQuit">В МЕНЮ</button>
    </div>
  </div>

  <div class="overlay" id="over">
    <h1 id="overTitle">СМЕНА ОКОНЧЕНА</h1>
    <div id="overStats"></div>
    <input id="playerName" maxlength="20" value="Gunkeeper">
    <div class="col">
      <button class="primary" id="btnSave">СОХРАНИТЬ РЕЗУЛЬТАТ</button>
      <button id="btnAgain">ИГРАТЬ СНОВА</button>
      <button id="btnMenu">В МЕНЮ</button>
    </div>
    <div id="scores"></div>
  </div>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js"
  }
}
</script>
<script type="module">
// ============================================================
import * as THREE from 'three';

// ============================================================
// КОНФИГ
// ============================================================
const VW = 960, VH = 600;
const WORLD_W = 1600, WORLD_H = 1000;
const BASE = { x: 800, y: 470, r: 46, hp: 150, max: 150 };
const CELL = 40;
const GC = Math.ceil(WORLD_W / CELL), GR = Math.ceil(WORLD_H / CELL);

const clamp = (v,a,b) => v<a?a:(v>b?b:v);
const rnd = (a,b) => a + Math.random()*(b-a);
const pick = arr => arr[(Math.random()*arr.length)|0];
const dist2 = (ax,ay,bx,by) => (ax-bx)*(ax-bx)+(ay-by)*(ay-by);
const dist = (ax,ay,bx,by) => Math.hypot(ax-bx, ay-by);

// ============================================================
// СЦЕНА
// ============================================================
const canvas = document.getElementById('game');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0c10);
scene.fog = new THREE.Fog(0x0a0c10, 900, 1800);

// top-down камера под углом
const camera = new THREE.PerspectiveCamera(50, VW/VH, 1, 3000);
const CAM_HEIGHT = 720;
const CAM_TILT = 0.95;
const camTarget = new THREE.Vector3(800, 0, 500);

function fit() {
  const s = Math.min(innerWidth/VW, innerHeight/VH);
  canvas.style.width = Math.floor(VW*s) + 'px';
  canvas.style.height = Math.floor(VH*s) + 'px';
  renderer.setSize(VW, VH, false);
}
addEventListener('resize', fit); fit();

// ============================================================
// СВЕТ
// ============================================================
scene.add(new THREE.AmbientLight(0x556070, 0.55));
const moon = new THREE.DirectionalLight(0x8899ff, 0.65);
moon.position.set(400, 800, 300);
moon.castShadow = true;
moon.shadow.mapSize.set(2048, 2048);
const sc = moon.shadow.camera;
sc.left=-900; sc.right=900; sc.top=900; sc.bottom=-900; sc.near=1; sc.far=2000;
scene.add(moon);

const lampPositions = [[-200,-200],[200,-200],[-200,200],[200,200],[0,0]];
const lampLights = [];
for (const [x,z] of lampPositions) {
  const l = new THREE.PointLight(0xffaa55, 1.4, 280, 2);
  l.position.set(800+x, 90, 500+z);
  l.castShadow = false;
  scene.add(l);
  lampLights.push(l);
}

// ============================================================
// ТЕКСТУРЫ (процедурные)
// ============================================================
function makeFloorTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#26282c'; g.fillRect(0,0,256,256);
  for (let i=0;i<4000;i++){const v=30+Math.random()*40;g.fillStyle=`rgb(${v},${v},${v+3})`;g.fillRect(Math.random()*256,Math.random()*256,2,2);}
  g.strokeStyle = 'rgba(0,0,0,.35)'; g.lineWidth = 2;
  for (let i=0;i<6;i++){g.beginPath();g.moveTo(0,i*42);g.lineTo(256,i*42);g.stroke();g.beginPath();g.moveTo(i*42,0);g.lineTo(i*42,256);g.stroke();}
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(WORLD_W/200, WORLD_H/200); return t;
}
function makeWallTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#3a3d42'; g.fillRect(0,0,256,256);
  for (let i=0;i<2500;i++){const v=40+Math.random()*30;g.fillStyle=`rgb(${v},${v},${v})`;g.fillRect(Math.random()*256,Math.random()*256,2,2);}
  g.strokeStyle = 'rgba(0,0,0,.4)'; g.lineWidth = 3;
  g.strokeRect(2,2,252,252);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
function makeCrateTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = '#6b4d2c'; g.fillRect(0,0,128,128);
  g.strokeStyle = '#3f2c18'; g.lineWidth = 4;
  g.strokeRect(3,3,122,122);
  g.beginPath(); g.moveTo(6,6); g.lineTo(122,122); g.moveTo(122,6); g.lineTo(6,122); g.stroke();
  const t = new THREE.CanvasTexture(c); return t;
}
const floorTex = makeFloorTexture();
const wallTex = makeWallTexture();
const crateTex = makeCrateTexture();

// ============================================================
// АРЕНА
// ============================================================
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(WORLD_W, WORLD_H),
  new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.95 })
);
floor.rotation.x = -Math.PI/2;
floor.receiveShadow = true;
scene.add(floor);

const obstacles = [
  { x:0, y:0, w:WORLD_W, h:40 },
  { x:0, y:WORLD_H-40, w:WORLD_W, h:40 },
  { x:0, y:0, w:40, h:WORLD_H },
  { x:WORLD_W-40, y:0, w:40, h:WORLD_H },
  { x:620, y:330, w:360, h:26 },
  { x:620, y:330, w:26, h:230 },
  { x:954, y:330, w:26, h:230 },
  { x:620, y:534, w:120, h:26 },
  { x:880, y:534, w:100, h:26 },
  { x:280, y:180, w:140, h:40 }, { x:280, y:180, w:40, h:140 },
  { x:1180, y:700, w:160, h:50 },
  { x:1240, y:280, w:50, h:160 },
  { x:180, y:780, w:110, h:110 },
  { x:1330, y:130, w:120, h:120 },
  { x:480, y:110, w:60, h:170 },
  { x:680, y:850, w:220, h:40 },
  { x:1060, y:400, w:60, h:130 },
  { x:260, y:600, w:60, h:130 },
  { x:1400, y:420, w:120, h:50 },
  { x:100, y:420, w:140, h:40 },
  { x:1240, y:900, w:100, h:60 }
];

const colliderBoxes = [];
const wallMat = new THREE.MeshStandardMaterial({ map: wallTex, roughness: 0.9 });
obstacles.forEach((o,i)=>{
  const isCrate = i >= 10;
  const h = isCrate ? 48 : (i < 4 ? 140 : 90);
  const mat = isCrate ? new THREE.MeshStandardMaterial({ map: crateTex, roughness: 0.9 }) : wallMat;
  const m = new THREE.Mesh(new THREE.BoxGeometry(o.w, h, o.h), mat);
  m.position.set(o.x + o.w/2, h/2, o.y + o.h/2);
  m.castShadow = true; m.receiveShadow = true;
  scene.add(m);
  colliderBoxes.push({ o, h });
});

function rectCircle(ox, oy, r, o) {
  const cx = clamp(ox, o.x, o.x+o.w), cy = clamp(oy, o.y, o.y+o.h);
  return (ox-cx)*(ox-cx) + (oy-cy)*(oy-cy) < r*r;
}
function isFree(x, y, r) {
  for (const o of obstacles) if (rectCircle(x,y,r,o)) return false;
  return true;
}

// ============================================================
// FLOW FIELD
// ============================================================
const blocked = new Uint8Array(GC*GR);
const fBase = new Int32Array(GC*GR);
const fPlayer = new Int32Array(GC*GR);
const NX = [1,-1,0,0,1,1,-1,-1];
const NY = [0,0,1,-1,1,-1,1,-1];
const ci = (cx,cy) => cy*GC + cx;

function buildGrid() {
  for (let cy=0; cy<GR; cy++) for (let cx=0; cx<GC; cx++) {
    const x0 = cx*CELL, y0 = cy*CELL, x1 = x0+CELL, y1 = y0+CELL;
    let b = 0;
    for (const o of obstacles) {
      if (x1 > o.x-16 && x0 < o.x+o.w+16 && y1 > o.y-16 && y0 < o.y+o.h+16) { b = 1; break; }
    }
    blocked[ci(cx,cy)] = b;
  }
}
function computeField(tx, ty, field) {
  field.fill(-1);
  let cx = clamp(Math.floor(tx/CELL), 0, GC-1), cy = clamp(Math.floor(ty/CELL), 0, GR-1);
  let start = ci(cx,cy);
  if (blocked[start]) {
    let found = -1;
    for (let r=1; r<10 && found<0; r++) {
      for (let dy=-r; dy<=r && found<0; dy++) for (let dx=-r; dx<=r && found<0; dx++) {
        const nx = cx+dx, ny = cy+dy;
        if (nx<0||ny<0||nx>=GC||ny>=GR) continue;
        if (!blocked[ci(nx,ny)]) found = ci(nx,ny);
      }
    }
    if (found < 0) return;
    start = found;
  }
  const q = new Int32Array(GC*GR);
  let qh = 0, qt = 0;
  field[start] = 0; q[qt++] = start;
  while (qh < qt) {
    const cur = q[qh++], ccx = cur % GC, ccy = (cur - ccx)/GC, d = field[cur] + 1;
    for (let i=0;i<8;i++) {
      const nx = ccx+NX[i], ny = ccy+NY[i];
      if (nx<0||ny<0||nx>=GC||ny>=GR) continue;
      const ni = ci(nx,ny);
      if (blocked[ni] || field[ni] >= 0) continue;
      if (i>=4 && (blocked[ci(ccx+NX[i],ccy)] || blocked[ci(ccx,ccy+NY[i])])) continue;
      field[ni] = d; q[qt++] = ni;
    }
  }
}
const dirOut = { x:0, y:0 };
function fieldDir(field, x, y) {
  const cx = clamp(Math.floor(x/CELL), 0, GC-1), cy = clamp(Math.floor(y/CELL), 0, GR-1);
  let best = Infinity, bx = cx, by = cy;
  for (let dy=-1; dy<=1; dy++) for (let dx=-1; dx<=1; dx++) {
    if (!dx && !dy) continue;
    const nx = cx+dx, ny = cy+dy;
    if (nx<0||ny<0||nx>=GC||ny>=GR) continue;
    if (blocked[ci(nx,ny)]) continue;
    if (dx && dy && (blocked[ci(cx+dx,cy)] || blocked[ci(cx,cy+dy)])) continue;
    const v = field[ci(nx,ny)];
    if (v < 0) continue;
    if (v < best) { best = v; bx = nx; by = ny; }
  }
  if (best === Infinity) { dirOut.x = 0; dirOut.y = 0; return false; }
  dirOut.x = (bx*CELL + CELL/2) - x;
  dirOut.y = (by*CELL + CELL/2) - y;
  const l = Math.hypot(dirOut.x, dirOut.y) || 1;
  dirOut.x /= l; dirOut.y /= l;
  return true;
}

// ============================================================
// ОРУЖИЕ / ТИПЫ ЗОМБИ
// ============================================================
const WEAPONS = [
  { id:'revolver', name:'РЕВОЛЬВЕР', dmg:30, rof:0.30, mag:6, reload:1.3, pellets:1, spread:0.035, range:950, price:0, col:0xe8c96a },
  { id:'smg', name:'ПИСТОЛЕТ-ПУЛЕМЁТ', dmg:16, rof:0.085, mag:30, reload:1.5, pellets:1, spread:0.085, range:820, price:420, col:0x9ad3ff },
  { id:'shotgun', name:'ДРОБОВИК', dmg:15, rof:0.75, mag:6, reload:2.1, pellets:7, spread:0.24, range:430, price:560, col:0xffb066 },
  { id:'rifle', name:'КАРАБИН', dmg:58, rof:0.5, mag:8, reload:1.9, pellets:1, spread:0.022, range:1200, price:900, col:0xb9ff9a },
  { id:'minigun', name:'МИНИГАН', dmg:19, rof:0.048, mag:120, reload:3.0, pellets:1, spread:0.115, range:820, price:1500, col:0xff9ad3 }
];
const ZTYPES = {
  walker: { hp:62, speed:54, r:15, dmg:9, money:12, col:0x6f9b42, head:0x8bbd55, scale:1 },
  runner: { hp:40, speed:122, r:13, dmg:7, money:17, col:0xd1833a, head:0xf0a55a, scale:0.9 },
  brute:  { hp:250, speed:38, r:22, dmg:24, money:48, col:0x9b5a5a, head:0xb87070, scale:1.35 },
  spitter:{ hp:80, speed:46, r:15, dmg:0, money:26, col:0x7a5bb5, head:0xa184e0, scale:1 },
  boss:   { hp:950, speed:44, r:36, dmg:34, money:260, col:0xb02fb0, head:0xe060e0, scale:2.0 }
};

// ============================================================
// СОСТОЯНИЕ
// ============================================================
const G = { mode:'menu', wave:0, money:0, kills:0, score:0, earned:0, queue:[], spawnT:0, waveActive:false, dmgLvl:0, rateLvl:0, shake:0, hurtT:0, time:0, navT:0 };
const P = { x:800, y:690, r:16, hp:100, max:100, ang:-Math.PI/2, weapon:0, mag:{}, reloadT:0, cd:0, inv:0, run:false, dead:false };
const owned = new Set(['revolver']);
const reserve = {}; WEAPONS.forEach(w => reserve[w.id] = 0);
WEAPONS.forEach(w => P.mag[w.id] = w.mag);

const zombies = [];
const tracers = [];
const parts = [];
const pickups = [];
const turrets = [];
const acid = [];
const TURRET_SLOTS = [{x:700,y:300},{x:900,y:300},{x:700,y:600},{x:900,y:600}];

// ============================================================
// 3D-МОДЕЛИ
// ============================================================
const playerGroup = new THREE.Group();
scene.add(playerGroup);
const pBody = new THREE.Mesh(new THREE.BoxGeometry(26, 30, 22), new THREE.MeshStandardMaterial({ color: 0x3f5d8a, roughness: 0.8 }));
pBody.position.y = 15; pBody.castShadow = true; playerGroup.add(pBody);
const pHead = new THREE.Mesh(new THREE.SphereGeometry(9, 12, 12), new THREE.MeshStandardMaterial({ color: 0xd8b089 }));
pHead.position.y = 38; pHead.castShadow = true; playerGroup.add(pHead);

const weaponMeshes = {};
WEAPONS.forEach(w => {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(6, 6, 26), new THREE.MeshStandardMaterial({ color: 0x22262b, metalness: 0.6, roughness: 0.4 }));
  body.position.z = -16; body.castShadow = true; g.add(body);
  const tip = new THREE.Mesh(new THREE.BoxGeometry(7, 7, 6), new THREE.MeshStandardMaterial({ color: w.col, metalness: 0.7 }));
  tip.position.z = -30; g.add(tip);
  g.visible = false;
  playerGroup.add(g);
  weaponMeshes[w.id] = g;
});
weaponMeshes.revolver.visible = true;

const baseGroup = new THREE.Group();
scene.add(baseGroup);
const baseFloor = new THREE.Mesh(new THREE.CylinderGeometry(46, 46, 4, 24), new THREE.MeshStandardMaterial({ color: 0x8d7a4c, roughness: 0.9 }));
baseFloor.position.set(BASE.x, 2, BASE.y); baseFloor.receiveShadow = true; baseGroup.add(baseFloor);
for (let i=0;i<8;i++) {
  const a = (i/8)*Math.PI*2;
  const s = new THREE.Mesh(new THREE.SphereGeometry(11, 8, 8), new THREE.MeshStandardMaterial({ color: 0x7a6a42, roughness: 0.9 }));
  s.position.set(BASE.x + Math.cos(a)*56, 10, BASE.y + Math.sin(a)*52);
  s.castShadow = true; baseGroup.add(s);
}
const baseCore = new THREE.Mesh(new THREE.BoxGeometry(68, 56, 68), new THREE.MeshStandardMaterial({ color: 0x3a4048, roughness: 0.8 }));
baseCore.position.set(BASE.x, 28, BASE.y); baseCore.castShadow = true; baseGroup.add(baseCore);
const baseLight = new THREE.PointLight(0xffd27a, 1.8, 260, 2);
baseLight.position.set(BASE.x, 80, BASE.y); baseGroup.add(baseLight);

const turretMeshes = {};
function createTurretMesh(i) {
  const s = TURRET_SLOTS[i];
  const g = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(12,14,10,10), new THREE.MeshStandardMaterial({ color: 0x2f3a3a }));
  base.position.y = 5; base.castShadow = true; g.add(base);
  const head = new THREE.Mesh(new THREE.BoxGeometry(22,12,22), new THREE.MeshStandardMaterial({ color: 0x8d9498 }));
  head.position.y = 16; head.castShadow = true; g.add(head);
  const barrel = new THREE.Mesh(new THREE.BoxGeometry(6,6,28), new THREE.MeshStandardMaterial({ color: 0xc9a24a }));
  barrel.position.set(0,16,-16); g.add(barrel);
  g.position.set(s.x, 0, s.y);
  scene.add(g);
  return { g, head, barrel };
}

// ============================================================
// ВВОД
// ============================================================
const keys = Object.create(null);
const mouse = { x: VW/2, y: VH/2, down: false };

function keyDir(e) {
  const c = e.code || '';
  if (c === 'KeyW' || c === 'ArrowUp') return 'up';
  if (c === 'KeyS' || c === 'ArrowDown') return 'down';
  if (c === 'KeyA' || c === 'ArrowLeft') return 'left';
  if (c === 'KeyD' || c === 'ArrowRight') return 'right';
  const k = (e.key || '').toLowerCase();
  if (k === 'w' || k === 'ц') return 'up';
  if (k === 's' || k === 'ы') return 'down';
  if (k === 'a' || k === 'ф') return 'left';
  if (k === 'd' || k === 'в') return 'right';
  return null;
}
addEventListener('keydown', e => {
  const d = keyDir(e);
  if (d) { keys[d] = true; e.preventDefault(); }
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') { keys.run = true; e.preventDefault(); }
  if (e.code === 'KeyR') { e.preventDefault(); startReload(); }
  if (e.code === 'Escape' || e.code === 'KeyP') { e.preventDefault(); togglePause(); }
  const m = /^Digit([1-5])$/.exec(e.code || '');
  if (m) { e.preventDefault(); selectWeapon(+m[1]-1); }
}, { passive: false });
addEventListener('keyup', e => {
  const d = keyDir(e);
  if (d) keys[d] = false;
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') keys.run = false;
});
addEventListener('blur', () => { for (const k in keys) keys[k] = false; mouse.down = false; });

function toLogical(e) {
  const r = canvas.getBoundingClientRect();
  return { x: (e.clientX - r.left) * VW / r.width, y: (e.clientY - r.top) * VH / r.height };
}
canvas.addEventListener('mousemove', e => { const p = toLogical(e); mouse.x = p.x; mouse.y = p.y; });
canvas.addEventListener('mousedown', e => {
  if (e.button === 0) { mouse.down = true; const p = toLogical(e); mouse.x = p.x; mouse.y = p.y; }
});
addEventListener('mouseup', e => { if (e.button === 0) mouse.down = false; });
canvas.addEventListener('contextmenu', e => e.preventDefault());
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const i = (P.weapon + (e.deltaY > 0 ? 1 : -1) + WEAPONS.length) % WEAPONS.length;
  selectWeapon(i);
}, { passive: false });

function selectWeapon(i) {
  if (i < 0 || i >= WEAPONS.length) return;
  if (!owned.has(WEAPONS[i].id)) return;
  P.weapon = i; P.reloadT = 0;
  WEAPONS.forEach(w => weaponMeshes[w.id].visible = false);
  weaponMeshes[WEAPONS[i].id].visible = true;
  updateHUD();
}
function startReload() {
  if (G.mode !== 'play') return;
  const w = WEAPONS[P.weapon];
  if (P.reloadT > 0 || P.mag[w.id] >= w.mag) return;
  if (reserve[w.id] <= 0) { SFX.empty(); return; }
  P.reloadT = w.reload; SFX.reload();
}

// ============================================================
// КАМЕРА / ПРОЕКЦИЯ
// ============================================================
const _v = new THREE.Vector3();
function screenToWorld(sx, sy) {
  const ndcX = (sx / VW) * 2 - 1;
  const ndcY = -(sy / VH) * 2 + 1;
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera);
  const plane = new THREE.Plane(new THREE.Vector3(0,1,0), 0);
  const hit = new THREE.Vector3();
  raycaster.ray.intersectPlane(plane, hit);
  return { x: hit.x, y: hit.z };
}
function updateCamera() {
  const tx = P.x, tz = P.y;
  camTarget.x += (tx - camTarget.x) * 0.15;
  camTarget.z += (tz - camTarget.z) * 0.15;
  const shake = G.shake;
  const sx = shake ? rnd(-shake, shake) : 0;
  const sz = shake ? rnd(-shake, shake) : 0;
  camera.position.set(camTarget.x + sx, CAM_HEIGHT, camTarget.z + CAM_HEIGHT * Math.sin(CAM_TILT) + sz);
  camera.lookAt(camTarget.x + sx, 0, camTarget.z + sz);
  camera.lookAt(camTarget.x, 0, camTarget.z);
}

// ============================================================
// ЗВУК
// ============================================================
let AC = null;
function ac() {
  if (!AC) { try { AC = new (window.AudioContext || window.webkitAudioContext)(); } catch(e){} }
  if (AC && AC.state === 'suspended') AC.resume();
  return AC;
}
function tone(freq, dur, type, vol) {
  const a = ac(); if (!a) return;
  try {
    const o = a.createOscillator(), g = a.createGain();
    o.type = type || 'square';
    o.frequency.setValueAtTime(freq, a.currentTime);
    o.frequency.exponentialRampToValueAtTime(Math.max(40, freq*0.5), a.currentTime + dur);
    g.gain.setValueAtTime(vol || 0.16, a.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, a.currentTime + dur);
    o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + dur + 0.02);
  } catch(e){}
}
const SFX = {
  shot: () => { tone(240,0.07,'square',0.18); tone(90,0.11,'sawtooth',0.10); },
  shotgun: () => { tone(150,0.16,'sawtooth',0.22); },
  reload: () => { tone(420,0.06,'square',0.10); setTimeout(()=>tone(600,0.06,'square',0.10),130); },
  empty: () => tone(300,0.05,'square',0.08),
  hit: () => tone(760,0.05,'sine',0.12),
  die: () => tone(90,0.25,'sawtooth',0.14),
  hurt: () => tone(140,0.22,'square',0.18),
  buy: () => { tone(600,0.06,'square',0.12); setTimeout(()=>tone(900,0.08,'square',0.12),90); },
  wave: () => { tone(220,0.18,'sawtooth',0.13); setTimeout(()=>tone(330,0.22,'sawtooth',0.13),170); },
  boom: () => tone(70,0.35,'sawtooth',0.22)
};

// ============================================================
// ЧАСТИЦЫ (3D-пулы)
// ============================================================
const partPools = { blood:[], dust:[], shell:[], flash:[] };
const particleGeoms = {
  blood: new THREE.SphereGeometry(2, 6, 6),
  dust: new THREE.SphereGeometry(2, 4, 4),
  shell: new THREE.CylinderGeometry(1, 1, 3, 6),
  flash: new THREE.SphereGeometry(10, 8, 8)
};
const particleMats = {
  blood: new THREE.MeshBasicMaterial({ color: 0xaa1818 }),
  dust: new THREE.MeshBasicMaterial({ color: 0x9a9384 }),
  shell: new THREE.MeshStandardMaterial({ color: 0xd9b64a, metalness: 0.8, roughness: 0.3 }),
  flash: new THREE.MeshBasicMaterial({ color: 0xffdd88, transparent: true, opacity: 0.9 })
};
function spawnPart(type, x, z, vx, vz, life) {
  let p = partPools[type].find(q => q.dead);
  if (!p) {
    const m = new THREE.Mesh(particleGeoms[type], particleMats[type]);
    p = { mesh: m, dead: true };
    scene.add(m);
    partPools[type].push(p);
  }
  p.dead = false;
  p.life = life; p.maxLife = life;
  p.mesh.position.set(x, 8, z);
  p.mesh.visible = true;
  p.vx = vx; p.vz = vz;
  if (type === 'flash') { p.mesh.scale.setScalar(0.1); }
}
function updateParts(dt) {
  for (const type in partPools) for (const p of partPools[type]) {
    if (p.dead) continue;
    p.life -= dt;
    if (p.life <= 0) { p.dead = true; p.mesh.visible = false; continue; }
    p.mesh.position.x += p.vx * dt;
    p.mesh.position.z += p.vz * dt;
    p.mesh.position.y += (type === 'blood' ? -60 : type === 'shell' ? 80 : 0) * dt;
    if (p.mesh.position.y < 1) { p.mesh.position.y = 1; p.vx *= 0.8; p.vz *= 0.8; }
    if (type === 'flash') {
      const t = p.life / p.maxLife;
      p.mesh.scale.setScalar(0.1 + (1 - t) * 1.8);
      p.mesh.material.opacity = t;
    }
    if (type === 'shell') p.mesh.rotation.x += dt * 12;
  }
}

// ============================================================
// ТРАССЕРЫ (линии)
// ============================================================
const tracerMat = new THREE.LineBasicMaterial({ color: 0xffd88a, transparent: true, opacity: 0.9 });
const tracerGeo = new THREE.BufferGeometry();
tracerGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
const tracerLine = new THREE.Line(tracerGeo, tracerMat);
tracerLine.visible = false;
scene.add(tracerLine);
function showTracer(x1, z1, x2, z2) {
  const pos = tracerGeo.attributes.position.array;
  pos[0]=x1; pos[1]=12; pos[2]=z1;
  pos[3]=x2; pos[4]=12; pos[5]=z2;
  tracerGeo.attributes.position.needsUpdate = true;
  tracerLine.visible = true;
  clearTimeout(tracerLine._t);
  tracerLine._t = setTimeout(() => { tracerLine.visible = false; }, 60);
}

// ============================================================
// ЗОМБИ (3D)
// ============================================================
function spawnZombie(type) {
  const t = ZTYPES[type];
  let x=0, y=0, ok=false;
  for (let att=0; att<60 && !ok; att++) {
    const edge = (Math.random()*4)|0;
    if (edge===0) { x = rnd(70, WORLD_W-70); y = rnd(70, 140); }
    else if (edge===1) { x = rnd(70, WORLD_W-70); y = rnd(WORLD_H-140, WORLD_H-70); }
    else if (edge===2) { x = rnd(70, 140); y = rnd(70, WORLD_H-70); }
    else { x = rnd(WORLD_W-140, WORLD_W-70); y = rnd(70, WORLD_H-70); }
    if (isFree(x, y, t.r+3) && dist(x, y, P.x, P.y) > 320) ok = true;
  }
  if (!ok) { x = 90; y = WORLD_H-90; }
  const wave = 1 + (G.wave-1)*0.16;
  const g = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: t.col, roughness: 0.9 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(24*t.scale, 36*t.scale, 20*t.scale), bodyMat);
  body.position.y = 18*t.scale; body.castShadow = true; g.add(body);
  const headMat = new THREE.MeshStandardMaterial({ color: t.head });
  const head = new THREE.Mesh(new THREE.SphereGeometry(10*t.scale, 10, 10), headMat);
  head.position.y = 46*t.scale; head.castShadow = true; g.add(head);
  const eyeMat = new THREE.MeshBasicMaterial({ color: 0xff3020 });
  const eyeL = new THREE.Mesh(new THREE.SphereGeometry(2.2, 6, 6), eyeMat);
  eyeL.position.set(-4*t.scale, 48*t.scale, 8*t.scale); g.add(eyeL);
  const eyeR = new THREE.Mesh(new THREE.SphereGeometry(2.2, 6, 6), eyeMat);
  eyeR.position.set(4*t.scale, 48*t.scale, 8*t.scale); g.add(eyeR);
  if (type === 'boss') {
    const crown = new THREE.Mesh(new THREE.TorusGeometry(11*t.scale, 2, 6, 16), new THREE.MeshBasicMaterial({ color: 0xffb0f0 }));
    crown.rotation.x = Math.PI/2; crown.position.y = 56*t.scale; g.add(crown);
  }
  g.position.set(x, 0, y);
  scene.add(g);
  zombies.push({
    type, x, y, r: t.r, hp: t.hp*wave, max: t.hp*wave,
    speed: t.speed * (1 + (G.wave-1)*0.035),
    dmg: t.dmg, money: t.money, col: t.col, head: t.head, scale: t.scale,
    kx:0, ky:0, flash:0, atkCd: rnd(0,0.6), state:'walk', anim: rnd(0,6),
    aggro:false, shotCd: rnd(1,3), dead:false, mesh:g,
    bodyMesh: body, headMesh: head
  });
}
function killZombie(z) {
  if (z.dead) return;
  z.dead = true;
  G.kills++; G.money += z.money; G.earned += z.money;
  spawnBloodBurst(z.x, z.y, 16);
  scene.remove(z.mesh);
  SFX.die();
  if (Math.random()<0.10) pickups.push({ x:z.x, y:z.y, type:'med', life:25, mesh: makePickupMesh('med') });
  else if (Math.random()<0.14) pickups.push({ x:z.x, y:z.y, type:'ammo', life:25, mesh: makePickupMesh('ammo') });
  updateHUD();
}
function makePickupMesh(type) {
  const g = new THREE.Group();
  if (type === 'med') {
    const b = new THREE.Mesh(new THREE.BoxGeometry(14,14,14), new THREE.MeshStandardMaterial({ color: 0xf0f0f0 }));
    b.castShadow = true; g.add(b);
    const c1 = new THREE.Mesh(new THREE.BoxGeometry(4,14,4), new THREE.MeshBasicMaterial({ color: 0xd03030 }));
    g.add(c1);
    const c2 = new THREE.Mesh(new THREE.BoxGeometry(14,4,4), new THREE.MeshBasicMaterial({ color: 0xd03030 }));
    g.add(c2);
  } else {
    const b = new THREE.Mesh(new THREE.BoxGeometry(16,10,12), new THREE.MeshStandardMaterial({ color: 0xb8862c }));
    b.castShadow = true; g.add(b);
    const c = new THREE.Mesh(new THREE.BoxGeometry(8,6,13), new THREE.MeshBasicMaterial({ color: 0x3a2c10 }));
    g.add(c);
  }
  g.position.y = 10;
  scene.add(g);
  return g;
}
function spawnBloodBurst(x, z, n) {
  for (let i=0;i<n;i++) spawnPart('blood', x, z, rnd(-90,90), rnd(-90,90), rnd(0.25,0.55));
}

// ============================================================
// СТРЕЛЬБА
// ============================================================
function rayCircle(ox, oz, dx, dz, cx, cz, r) {
  const fx = ox-cx, fz = oz-cz;
  const a = dx*dx + dz*dz, b = 2*(fx*dx + fz*dz), c = fx*fx + fz*fz - r*r;
  const disc = b*b - 4*a*c;
  if (disc < 0) return -1;
  const sq = Math.sqrt(disc);
  let t = (-b-sq)/(2*a);
  if (t < 0) t = (-b+sq)/(2*a);
  return t >= 0 ? t : -1;
}
function rayRect(ox, oz, dx, dz, o) {
  let tmin = 0, tmax = Infinity;
  for (let ax=0; ax<2; ax++) {
    const o0 = ax===0?ox:oz, d0 = ax===0?dx:dz;
    const o1 = ax===0?o.x:o.y, o2 = ax===0?o.x+o.w:o.y+o.h;
    if (Math.abs(d0)<1e-6) { if (o0<o1||o0>o2) return -1; continue; }
    let t1 = (o1-o0)/d0, t2 = (o2-o0)/d0;
    if (t1>t2){const tt=t1;t1=t2;t2=tt;}
    if (t1>tmin) tmin=t1;
    if (t2<tmax) tmax=t2;
    if (tmin>tmax) return -1;
  }
  return tmin>=0?tmin:(tmax>=0?0:-1);
}
function fire() {
  const w = WEAPONS[P.weapon];
  if (P.reloadT > 0 || P.cd > 0 || P.dead) return;
  if (P.mag[w.id] <= 0) { startReload(); return; }
  P.mag[w.id]--;
  P.cd = w.rof / (1 + 0.08*G.rateLvl);
  const dmg = w.dmg * (1 + 0.12*G.dmgLvl);
  const aim = screenToWorld(mouse.x, mouse.y);
  const baseAng = Math.atan2(aim.y - P.y, aim.x - P.x);
  P.ang = baseAng;
  if (w.id === 'shotgun') SFX.shotgun(); else SFX.shot();
  G.shake = Math.min(9, G.shake + (w.id === 'shotgun' ? 6 : 2));
  playerGroup.rotation.y = -baseAng + Math.PI/2;
  for (let i=0;i<w.pellets;i++) {
    const a = baseAng + rnd(-w.spread, w.spread);
    const dx = Math.cos(a), dz = Math.sin(a);
    const ox = P.x + dx*20, oz = P.y + dz*20;
    let bestT = w.range, hitZ = null;
    for (const z of zombies) {
      if (z.dead) continue;
      const t = rayCircle(ox, oz, dx, dz, z.x, z.y, z.r);
      if (t >= 0 && t < bestT) { bestT = t; hitZ = z; }
    }
    let wallT = w.range;
    for (const o of obstacles) { const t = rayRect(ox, oz, dx, dz, o); if (t >= 0 && t < wallT) wallT = t; }
    const endT = Math.min(bestT, wallT);
    showTracer(ox, oz, ox+dx*endT, oz+dz*endT);
    if (hitZ && bestT <= wallT) {
      hitZ.hp -= dmg;
      hitZ.flash = 0.12;
      hitZ.kx += dx*60; hitZ.ky += dz*60;
      spawnBloodBurst(hitZ.x + dx*hitZ.r, hitZ.y + dz*hitZ.r, 5);
      SFX.hit();
      if (hitZ.hp <= 0) killZombie(hitZ);
    } else if (wallT < w.range) {
      for (let j=0;j<3;j++) spawnPart('dust', ox+dx*wallT, oz+dz*wallT, rnd(-40,40), rnd(-40,40), rnd(0.2,0.45));
    }
  }
  spawnPart('shell', P.x, P.y, -Math.sin(baseAng)*rnd(60,120)+rnd(-30,30), -Math.cos(baseAng)*rnd(60,120), 0.9);
  spawnPart('flash', P.x + Math.cos(baseAng)*26, P.y + Math.sin(baseAng)*26, 0, 0, 0.07);
  updateHUD();
}

function hurtPlayer(dmg) {
  if (P.inv > 0 || P.dead) return;
  P.hp -= dmg; P.inv = 0.55; G.shake = 12; G.hurtT = 0.35; SFX.hurt();
  if (P.hp <= 0) { P.hp = 0; P.dead = true; gameOver('ВЫ ПОГИБЛИ'); }
  updateHUD();
}
function hurtBase(dmg) {
  if (BASE.hp <= 0) return;
  BASE.hp -= dmg;
  for (let i=0;i<4;i++) spawnPart('dust', BASE.x + rnd(-30,30), BASE.y + rnd(-30,30), rnd(-40,40), rnd(-40,40), 0.4);
  if (BASE.hp <= 0) { BASE.hp = 0; gameOver('СКЛАД ПАЛ'); }
  updateHUD();
}

// ============================================================
// ТУРЕЛИ
// ============================================================
function addTurret() {
  if (turrets.length >= TURRET_SLOTS.length) return false;
  const i = turrets.length;
  const m = createTurretMesh(i);
  turrets.push({ x: TURRET_SLOTS[i].x, y: TURRET_SLOTS[i].y, ang: -Math.PI/2, cd: 0, mesh: m });
  return true;
}

// ============================================================
// ВОЛНЫ
// ============================================================
function waveComposition(n) {
  const list = [];
  const walkers = 4 + Math.floor(n*1.3);
  for (let i=0;i<walkers;i++) list.push('walker');
  if (n>=2) { const r = 2 + Math.floor(n*0.5); for (let i=0;i<r;i++) list.push('runner'); }
  if (n>=4) { const b = Math.floor((n-2)/2); for (let i=0;i<b;i++) list.push('brute'); }
  if (n>=6) { const s = Math.floor((n-4)/2); for (let i=0;i<s;i++) list.push('spitter'); }
  if (n%5===0) list.push('boss');
  for (let i=list.length-1;i>0;i--){const j=(Math.random()*(i+1))|0;const t=list[i];list[i]=list[j];list[j]=t;}
  return list.slice(0, 46);
}
function startWave(n) {
  G.wave = n; G.queue = waveComposition(n); G.spawnT = 0.6; G.waveActive = true;
  G.mode = 'play';
  banner('ВОЛНА ' + n);
  SFX.wave();
  updateHUD();
}

// ============================================================
// МАГАЗИН
// ============================================================
function openShop() {
  G.mode = 'shop';
  const bonus = 40 + G.wave*14;
  G.money += bonus; G.earned += bonus;
  document.getElementById('shopTitle').textContent = 'МАГАЗИН — ВОЛНА ' + (G.wave+1);
  renderShop();
  document.getElementById('shop').classList.add('active');
  updateHUD();
}
function renderShop() {
  const body = document.getElementById('shopBody');
  body.innerHTML = '';
  const add = (title, sub, cost, act, disabled) => {
    const b = document.createElement('button');
    b.className = 'shopItem';
    b.innerHTML = '<b>'+title+'</b><small>'+sub+'</small>';
    b.disabled = !!disabled;
    b.addEventListener('click', act);
    body.appendChild(b);
  };
  WEAPONS.forEach((w,i)=>{
    if (owned.has(w.id)) return;
    add(w.name, 'Урон '+w.dmg+' • магаз '+w.mag+' — $'+w.price, w.price, ()=>buyWeapon(i), G.money < w.price);
  });
  const cw = WEAPONS[P.weapon];
  add('ПАТРОНЫ: '+cw.name, '2 магазина — $'+(cw.mag*8), cw.mag*8, ()=>buyAmmo(cw), G.money < cw.mag*8 || reserve[cw.id] >= cw.mag*12);
  add('АПТЕЧКА +50 HP', 'мгновенно — $60', 60, ()=>buyMed(), G.money<60 || P.hp>=P.max);
  add('РЕМОНТ СКЛАДА +50', 'укрепить — $70', 70, ()=>buyRepair(), G.money<70 || BASE.hp>=BASE.max);
  add('ТУРЕЛЬ ($300)', 'макс. '+TURRET_SLOTS.length, 300, ()=>buyTurret(), G.money<300 || turrets.length>=TURRET_SLOTS.length);
  add('УЛУЧШИТЬ УРОН', 'ур. '+(G.dmgLvl+1)+' (+12%) — $'+(300+G.dmgLvl*220), 300+G.dmgLvl*220, ()=>buyDmg(), G.money<300+G.dmgLvl*220);
  add('УЛУЧШИТЬ ТЕМП', 'ур. '+(G.rateLvl+1)+' (+8%) — $'+(300+G.rateLvl*220), 300+G.rateLvl*220, ()=>buyRate(), G.money<300+G.rateLvl*220);
  document.getElementById('shopMoney').textContent = 'В кошельке: $'+G.money;
}
function buyWeapon(i) { const w = WEAPONS[i]; if (owned.has(w.id)||G.money<w.price) return; G.money-=w.price; owned.add(w.id); P.mag[w.id]=w.mag; reserve[w.id]+=w.mag*4; selectWeapon(i); SFX.buy(); renderShop(); updateHUD(); }
function buyAmmo(w) { const c=w.mag*8; if (G.money<c||reserve[w.id]>=w.mag*12) return; G.money-=c; reserve[w.id]+=w.mag*2; SFX.buy(); renderShop(); updateHUD(); }
function buyMed() { if (G.money<60||P.hp>=P.max) return; G.money-=60; P.hp=Math.min(P.max,P.hp+50); SFX.buy(); renderShop(); updateHUD(); }
function buyRepair() { if (G.money<70||BASE.hp>=BASE.max) return; G.money-=70; BASE.hp=Math.min(BASE.max,BASE.hp+50); SFX.buy(); renderShop(); updateHUD(); }
function buyTurret() { if (G.money<300||!addTurret()) return; G.money-=300; SFX.buy(); renderShop(); updateHUD(); }
function buyDmg() { const c=300+G.dmgLvl*220; if (G.money<c) return; G.money-=c; G.dmgLvl++; SFX.buy(); renderShop(); updateHUD(); }
function buyRate() { const c=300+G.rateLvl*220; if (G.money<c) return; G.money-=c; G.rateLvl++; SFX.buy(); renderShop(); updateHUD(); }

// ============================================================
// ОБНОВЛЕНИЕ МИРА
// ============================================================
function moveEntity(e, dx, dy, r) {
  e.x += dx;
  for (const o of obstacles) {
    if (e.x+r>o.x && e.x-r<o.x+o.w && e.y+r>o.y && e.y-r<o.y+o.h) {
      const l = (e.x+r)-o.x, rr = (o.x+o.w)-(e.x-r);
      e.x = l<rr ? o.x-r-0.01 : o.x+o.w+r+0.01;
    }
  }
  e.y += dy;
  for (const o of obstacles) {
    if (e.x+r>o.x && e.x-r<o.x+o.w && e.y+r>o.y && e.y-r<o.y+o.h) {
      const t = (e.y+r)-o.y, b = (o.y+o.h)-(e.y-r);
      e.y = t<b ? o.y-r-0.01 : o.y+o.h+r+0.01;
    }
  }
  e.x = clamp(e.x, r+4, WORLD_W-r-4);
  e.y = clamp(e.y, r+4, WORLD_H-r-4);
}

function update(dt) {
  G.time += dt;
  if (G.shake > 0) G.shake = Math.max(0, G.shake - dt*26);
  if (G.hurtT > 0) G.hurtT -= dt;

  let mx=0, my=0;
  if (keys.left) mx-=1; if (keys.right) mx+=1;
  if (keys.up) my-=1; if (keys.down) my+=1;
  const mlen = Math.hypot(mx,my);
  if (mlen > 0.001) { mx/=Math.max(1,mlen); my/=Math.max(1,mlen); }
  const spd = keys.run ? 235 : 165;
  moveEntity(P, mx*spd*dt, my*spd*dt, P.r);
  const aim = screenToWorld(mouse.x, mouse.y);
  P.ang = Math.atan2(aim.y-P.y, aim.x-P.x);

  if (P.cd > 0) P.cd -= dt;
  if (P.reloadT > 0) {
    P.reloadT -= dt;
    if (P.reloadT <= 0) {
      const w = WEAPONS[P.weapon];
      const need = w.mag - P.mag[w.id];
      const take = Math.min(need, reserve[w.id]);
      P.mag[w.id] += take; reserve[w.id] -= take;
      P.reloadT = 0; updateHUD();
    }
  }
  if (P.inv > 0) P.inv -= dt;
  if (mouse.down && G.mode === 'play') fire();

  playerGroup.position.set(P.x, 0, P.y);
  playerGroup.rotation.y = -P.ang + Math.PI/2;

  if (G.waveActive) {
    G.spawnT -= dt;
    if (G.spawnT <= 0 && G.queue.length && zombies.length < 70) {
      spawnZombie(G.queue.shift());
      G.spawnT = Math.max(0.22, 1.05 - G.wave*0.045);
    }
    if (!G.queue.length && !zombies.length) {
      G.waveActive = false;
      openShop();
      return;
    }
  }

  if (!G.navT || G.time - G.navT > 0.25) {
    G.navT = G.time;
    computeField(BASE.x, BASE.y, fBase);
    computeField(P.x, P.y, fPlayer);
  }

  for (const z of zombies) {
    if (z.dead) continue;
    z.anim += dt * (z.state==='walk'?6:2);
    if (z.flash > 0) z.flash -= dt;
    z.kx *= 0.86; z.ky *= 0.86;
    const dp = dist(z.x, z.y, P.x, P.y);
    const db = dist(z.x, z.y, BASE.x, BASE.y);
    z.aggro = dp < 240 && dp < db;
    let tx, ty, field;
    if (z.aggro) { tx=P.x; ty=P.y; field=fPlayer; }
    else { tx=BASE.x; ty=BASE.y; field=fBase; }
    const dTarget = z.aggro ? dp : db;

    if (z.type === 'spitter') {
      z.shotCd -= dt;
      if (dTarget < 420 && z.shotCd <= 0) {
        z.shotCd = 1.9;
        const a = Math.atan2(ty-z.y, tx-z.x);
        acid.push({ x:z.x, y:z.y, vx:Math.cos(a)*240, vy:Math.sin(a)*240, life:3, dmg:6, mesh: makeAcidMesh() });
      }
      if (dTarget < 170) {
        const a = Math.atan2(z.y-ty, z.x-tx);
        moveEntity(z, Math.cos(a)*z.speed*dt, Math.sin(a)*z.speed*dt, z.r);
        z.state='walk';
        if (z.mesh) { z.mesh.position.set(z.x, 0, z.y); }
        continue;
      }
    }

    if (dTarget < (z.aggro ? P.r+z.r+10 : BASE.r+z.r+12)) {
      z.state = 'attack';
      z.atkCd -= dt;
      if (z.atkCd <= 0) {
        z.atkCd = 1.0;
        if (z.aggro) {
          hurtPlayer(z.dmg);
          const a = Math.atan2(P.y-z.y, P.x-z.x);
          z.kx += Math.cos(a)*130; z.ky += Math.sin(a)*130;
        } else hurtBase(z.dmg);
      }
    } else {
      z.state = 'walk';
      let dirX=0, dirY=0;
      const got = fieldDir(field, z.x, z.y);
      if (got) { dirX = dirOut.x; dirY = dirOut.y; }
      else { const a = Math.atan2(ty-z.y, tx-z.x); dirX = Math.cos(a); dirY = Math.sin(a); }
      let sx=0, sy=0;
      for (const o of zombies) {
        if (o===z || o.dead) continue;
        const dx = z.x-o.x, dy = z.y-o.y;
        const dd = dx*dx+dy*dy;
        const min = (z.r+o.r)*1.05;
        if (dd < min*min && dd > 0.01) {
          const l = Math.sqrt(dd);
          sx += dx/l * (1-l/min)*0.9; sy += dy/l * (1-l/min)*0.9;
        }
      }
      dirX += sx; dirY += sy;
      const l = Math.hypot(dirX, dirY) || 1;
      dirX /= l; dirY /= l;
      moveEntity(z, (dirX*z.speed + z.kx)*dt, (dirY*z.speed + z.ky)*dt, z.r);
    }
    if (z.mesh) {
      z.mesh.position.set(z.x, 0, z.y);
      z.mesh.rotation.y = -Math.atan2(ty-z.y, tx-z.x) + Math.PI/2;
      if (z.flash > 0) {
        z.bodyMesh.material.emissive = new THREE.Color(0xffffff);
        z.bodyMesh.material.emissiveIntensity = z.flash*4;
      } else {
        z.bodyMesh.material.emissive = new THREE.Color(0x000000);
      }
    }
  }
  for (let i=zombies.length-1;i>=0;i--) if (zombies[i].dead) zombies.splice(i,1);

  for (let i=acid.length-1;i>=0;i--) {
    const a = acid[i];
    a.x += a.vx*dt; a.y += a.vy*dt; a.life -= dt;
    let gone = a.life <= 0;
    for (const o of obstacles) if (a.x>o.x && a.x<o.x+o.w && a.y>o.y && a.y<o.y+o.h) { gone = true; break; }
    if (!gone && dist(a.x,a.y,BASE.x,BASE.y) < BASE.r+6) { hurtBase(a.dmg); gone = true; }
    if (!gone && dist(a.x,a.y,P.x,P.y) < P.r+6) { hurtPlayer(a.dmg); gone = true; }
    if (a.mesh) { a.mesh.position.set(a.x, 6, a.y); }
    if (gone) { if (a.mesh) scene.remove(a.mesh); acid.splice(i,1); }
  }

  for (const t of turrets) {
    t.cd -= dt;
    let target = null, bd = 520;
    for (const z of zombies) {
      if (z.dead) continue;
      const d = dist(t.x,t.y,z.x,z.y);
      if (d < bd) { bd = d; target = z; }
    }
    if (target) {
      t.ang = Math.atan2(target.y-t.y, target.x-t.x);
      if (t.mesh) { t.mesh.g.rotation.y = -t.ang + Math.PI/2; t.mesh.head.rotation.y = 0; t.mesh.barrel.rotation.y = 0; }
      if (t.cd <= 0) {
        t.cd = 0.22;
        const dx = Math.cos(t.ang), dz = Math.sin(t.ang);
        const ox = t.x + dx*18, oz = t.y + dz*18;
        let bt = 520, bz = null;
        for (const z of zombies) { const tt = rayCircle(ox,oz,dx,dz,z.x,z.y,z.r); if (tt>=0 && tt<bt) { bt=tt; bz=z; } }
        let wt = 520;
        for (const o of obstacles) { const tt = rayRect(ox,oz,dx,dz,o); if (tt>=0 && tt<wt) wt=tt; }
        const et = Math.min(bt, wt);
        showTracer(ox, oz, ox+dx*et, oz+dz*et);
        if (bz && bt <= wt) { bz.hp -= 16*(1+0.12*G.dmgLvl); bz.flash = 0.1; spawnBloodBurst(bz.x, bz.y, 3); if (bz.hp <= 0) killZombie(bz); }
      }
    }
  }

  updateParts(dt);

  for (let i=pickups.length-1;i>=0;i--) {
    const k = pickups[i];
    k.life -= dt;
    if (k.mesh) { k.mesh.rotation.y += dt*3; k.mesh.position.y = 10 + Math.sin(G.time*4+i)*4; }
    if (dist(k.x,k.y,P.x,P.y) < 26) {
      if (k.type === 'med') { P.hp = Math.min(P.max, P.hp+25); spawnBloodBurst(k.x, k.y, 6); }
      else { const w = WEAPONS[P.weapon]; reserve[w.id] += w.mag; }
      if (k.mesh) scene.remove(k.mesh);
      pickups.splice(i,1); updateHUD(); continue;
    }
    if (k.life <= 0) { if (k.mesh) scene.remove(k.mesh); pickups.splice(i,1); }
  }

  updateCamera();
  updateLights(dt);
}

let lightT = 0;
function updateLights(dt) {
  lightT += dt;
  for (let i=0;i<lampLights.length;i++) {
    lampLights[i].intensity = 1.2 + Math.sin(lightT*3 + i)*0.25;
  }
}

function makeAcidMesh() {
  const m = new THREE.Mesh(new THREE.SphereGeometry(6, 8, 8), new THREE.MeshBasicMaterial({ color: 0x9be05a }));
  scene.add(m);
  return m;
}

// ============================================================
// HUD
// ============================================================
const el = id => document.getElementById(id);
function banner(txt) {
  el('banner').textContent = txt;
  el('banner').classList.add('show');
  setTimeout(() => el('banner').classList.remove('show'), 1600);
}
function updateHUD() {
  const w = WEAPONS[P.weapon];
  el('hpFill').style.width = Math.max(0, P.hp) + '%';
  el('hpText').textContent = 'HP ' + Math.max(0, Math.round(P.hp));
  el('baseFill').style.width = Math.max(0, BASE.hp/BASE.max*100) + '%';
  el('waveTxt').textContent = 'ВОЛНА ' + G.wave;
  el('money').textContent = '$' + G.money;
  el('kills').textContent = '☠ ' + G.kills;
  el('wName').textContent = w.name;
  el('aCount').textContent = P.mag[w.id];
  el('aCount').classList.toggle('low', P.mag[w.id] <= Math.max(2, w.mag*0.25));
  el('aRes').textContent = reserve[w.id] >= 9999 ? '∞' : ('/ ' + reserve[w.id]);
  el('reload').textContent = P.reloadT > 0 ? 'ПЕРЕЗАРЯДКА...' : '';
  const sl = el('slots');
  if (sl.children.length !== WEAPONS.length) {
    sl.innerHTML = '';
    WEAPONS.forEach((w2,i)=>{
      const d = document.createElement('div');
      d.className = 'slot';
      d.innerHTML = '<span>'+(i+1)+'</span><b>'+w2.name.split(' ')[0]+'</b>';
      sl.appendChild(d);
    });
  }
  [...sl.children].forEach((d,i)=>{
    d.classList.toggle('on', i===P.weapon);
    d.classList.toggle('lock', !owned.has(WEAPONS[i].id));
  });
}

// ============================================================
// РАДАР
// ============================================================
const radar = document.getElementById('radar');
const rctx = radar.getContext('2d');
function drawRadar() {
  const W = 132, s = W/WORLD_W;
  rctx.clearRect(0,0,W,W);
  rctx.fillStyle = 'rgba(10,12,16,.75)'; rctx.fillRect(0,0,W,W);
  rctx.fillStyle = '#3a4048';
  for (const o of obstacles) rctx.fillRect(o.x*s, o.y*s, o.w*s, o.h*s);
  rctx.fillStyle = '#d8b34a';
  rctx.fillRect((BASE.x-BASE.r)*s, (BASE.y-BASE.r)*s, BASE.r*2*s, BASE.r*2*s);
  for (const t of turrets) { rctx.fillStyle = '#9ad3ff'; rctx.fillRect(t.x*s-1, t.y*s-1, 3, 3); }
  for (const z of zombies) {
    if (z.dead) continue;
    rctx.fillStyle = z.type==='boss' ? '#ff40ff' : z.type==='brute' ? '#ff8060' : z.type==='runner' ? '#ffc040' : '#ff4040';
    rctx.fillRect(z.x*s-1, z.y*s-1, 3, 3);
  }
  rctx.fillStyle = '#60ff60';
  rctx.beginPath(); rctx.arc(P.x*s, P.y*s, 3, 0, 6.3); rctx.fill();
}

// ============================================================
// ПАУЗА / GAME OVER / МЕНЮ
// ============================================================
function togglePause() {
  if (G.mode === 'play') { G.mode = 'pause'; el('pause').classList.add('active'); mouse.down = false; }
  else if (G.mode === 'pause') { G.mode = 'play'; el('pause').classList.remove('active'); for (const k in keys) keys[k] = false; }
}
function resetGame() {
  P.x = 800; P.y = 690; P.r = 16; P.hp = P.max = 100; P.ang = -Math.PI/2;
  P.weapon = 0; P.reloadT = 0; P.cd = 0; P.inv = 0; P.dead = false;
  WEAPONS.forEach(w => P.mag[w.id] = w.mag);
  WEAPONS.forEach(w => reserve[w.id] = w.id === 'revolver' ? 9999 : 0);
  owned.clear(); owned.add('revolver');
  G.wave = 0; G.money = 150; G.kills = 0; G.score = 0; G.earned = 0;
  G.dmgLvl = 0; G.rateLvl = 0; G.shake = 0; G.hurtT = 0;
  zombies.length = 0; parts.length = 0; pickups.length = 0;
  turrets.length = 0; acid.length = 0; tracers.length = 0;
  for (const z of zombies) if (z.mesh) scene.remove(z.mesh);
  for (const k of pickups) if (k.mesh) scene.remove(k.mesh);
  for (const t of turrets) if (t.mesh) scene.remove(t.mesh.g);
  for (const a of acid) if (a.mesh) scene.remove(a.mesh);
  BASE.hp = BASE.max = 150;
  for (const k in keys) keys[k] = false;
  mouse.down = false;
  buildGrid();
  WEAPONS.forEach(w => weaponMeshes[w.id].visible = false);
  weaponMeshes.revolver.visible = true;
  updateHUD();
}
function startGame() {
  ac();
  resetGame();
  el('menu').classList.remove('active');
  el('hud').classList.add('active');
  startWave(1);
}
function gameOver(reason) {
  if (G.mode === 'over') return;
  G.mode = 'over';
  G.score = G.kills*10 + G.wave*120 + Math.round(BASE.hp);
  el('overTitle').textContent = reason;
  el('overStats').innerHTML =
    'Дожили до волны: <b>'+G.wave+'</b><br>'+
    'Убито зомби: <b>'+G.kills+'</b><br>'+
    'Заработано: <b>$'+G.earned+'</b><br>'+
    'Склад: <b>'+Math.round(BASE.hp)+'/'+BASE.max+'</b><br>'+
    'Счёт: <b>'+G.score+'</b>';
  el('over').classList.add('active');
  el('hud').classList.remove('active');
  mouse.down = false;
  loadTopScores();
}
function backToMenu() {
  G.mode = 'menu';
  el('over').classList.remove('active');
  el('shop').classList.remove('active');
  el('pause').classList.remove('active');
  el('hud').classList.remove('active');
  el('menu').classList.add('active');
}

el('btnStart').addEventListener('click', startGame);
el('btnHelp').addEventListener('click', () => {
  const h = el('helpText'); h.style.display = h.style.display === 'none' ? 'block' : 'none';
});
el('btnResume').addEventListener('click', togglePause);
el('btnQuit').addEventListener('click', backToMenu);
el('btnAgain').addEventListener('click', () => { el('over').classList.remove('active'); startGame(); });
el('btnMenu').addEventListener('click', backToMenu);
el('btnNextWave').addEventListener('click', () => { el('shop').classList.remove('active'); startWave(G.wave+1); });
el('btnSave').addEventListener('click', async () => {
  const name = (el('playerName').value || 'Gunkeeper').slice(0,20);
  try {
    await fetch('/api/scores', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ name, score: G.score })
    });
  } catch(e){}
  loadTopScores();
});
async function loadTopScores() {
  try {
    const r = await fetch('/api/scores');
    const data = await r.json();
    const box = el('scores');
    if (!data.scores || !data.scores.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<div style="color:#8a8f7a">ТОП-5</div>' +
      data.scores.slice(0,5).map((s,i)=>'<div>'+(i+1)+'. '+s.name+' — '+s.score+'</div>').join('');
  } catch(e){}
}

// ============================================================
// ЦИКЛ
// ============================================================
let last = performance.now();
function loop(ts) {
  requestAnimationFrame(loop);
  const dt = Math.min(0.05, (ts-last)/1000);
  last = ts;
  if (G.mode === 'play') update(dt);
  drawRadar();
  document.getElementById('vignette').style.opacity = G.hurtT > 0 ? '1' : (P.hp < 35 ? '0.45' : '0');
  renderer.render(scene, camera);
}
buildGrid();
updateHUD();
loadTopScores();
el('loadTip').style.display = 'none';
requestAnimationFrame(loop);
// ============================================================
</script>
</body>
</html>
"""


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
    name = str(data.get('name', 'Gunkeeper')).strip()[:MAX_NAME_LEN] or 'Gunkeeper'
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
    rank = next((i + 1 for i, s in enumerate(scores) if s['score'] == score and s['name'] == name), None)
    return {'ok': True, 'rank': rank}


@app.errorhandler(404)
def not_found(e):
    return Response(INDEX_HTML, mimetype='text/html')


if __name__ == '__main__':
    log.info('Gunkeeper3D: запуск на порту %s', PORT)
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG, threaded=True)
