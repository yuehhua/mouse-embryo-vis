import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

// Stages for the developmental slider (oldest -> youngest embryo left to right = earlier->later)
const STAGES = [
  { id: 'ts23', ts: 'TS23', age: 'E15', day: '~day 15' },
  { id: 'ts24', ts: 'TS24', age: 'E16', day: '~day 16' },
  { id: 'ts26', ts: 'TS26', age: 'E18', day: '~day 18' },
];
const QUIZ_STAGE = 'ts26';       // quiz uses the richest, most-recognizable stage
const ROUND_SIZE = 10;
const VIEW_SIZE = 900;           // every stage is scaled to this height so switching is smooth
const CTX_OPACITY = 0.22;        // translucent "jelly" body — readable position, not a faint shadow

const FACTS = {
  'EMAPA:16846': 'The liver — at this stage it is the main site of blood-cell production.',
  'EMAPA:16688': 'A heart atrium — the chambers that receive blood returning to the heart.',
  'EMAPA:17331': 'The heart ventricle — the muscular pump pushing blood to body and lungs.',
  'EMAPA:16728': 'The lung — fluid-filled in the embryo; it only inflates with air at birth.',
  'EMAPA:17373': 'The metanephros — the embryonic kidney that becomes the adult kidney.',
  'EMAPA:17021': 'The stomach — a muscular bag that begins the breakdown of food.',
  'EMAPA:17185': 'The tongue — packed with muscle; very muscular for its size.',
  'EMAPA:19143': 'The femur — the thigh bone, forming through cartilage before it ossifies.',
  'EMAPA:19106': 'The humerus — the upper forelimb bone.',
  'EMAPA:16895': 'The forebrain — becomes the cerebral hemispheres, the thinking brain.',
  'EMAPA:16974': 'The midbrain — relays vision, hearing and movement signals.',
  'EMAPA:16916': 'The hindbrain — becomes the cerebellum and brainstem (balance, breathing).',
  'EMAPA:17577': 'The spinal cord — the neural cable linking brain and body.',
  'EMAPA:18768': 'The thymus — where immune T-cells mature; largest early in life.',
  'EMAPA:18767': 'The spleen — filters blood and supports the immune system.',
  'EMAPA:17503': 'The pancreas — makes digestive enzymes and insulin.',
  'EMAPA:18321': 'The bladder — stores urine produced by the kidneys.',
  'EMAPA:17701': 'The diaphragm — the dome-shaped muscle that drives breathing.',
  'EMAPA:17838': 'The lens of the eye — a clear disc that focuses light onto the retina.',
  'EMAPA:18010': 'A rib — part of the cage protecting the heart and lungs.',
};

const $ = id => document.getElementById(id);
const view = $('view');

// ---- scene ----
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(view.clientWidth, view.clientHeight);
view.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(45, view.clientWidth / view.clientHeight, 1, 8000);
camera.position.set(0, 0, VIEW_SIZE * 2.1);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.5;

scene.add(new THREE.HemisphereLight(0xffffff, 0x39404d, 1.15));
const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(1, 1, 1.4); scene.add(key);
const fill = new THREE.DirectionalLight(0xffffff, 0.55); fill.position.set(-1, -0.6, -1); scene.add(fill);
const rim = new THREE.DirectionalLight(0x88aaff, 0.5); rim.position.set(0, 1, -1.2); scene.add(rim);

// ---- load all stages ----
const draco = new DRACOLoader();
draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
const loader = new GLTFLoader();
loader.setDRACOLoader(draco);

const stageData = new Map();   // id -> { group, organs: Map(emapa -> {mesh,name,rgb}) }

const keyFromNode = n => n.replace(/^EMAPA/, 'EMAPA:');

function loadStage(st) {
  return Promise.all([
    fetch(`./data/${st.id}.json`).then(r => r.json()),
    new Promise((res, rej) => loader.load(`./data/${st.id}.glb`, res, undefined, rej)),
  ]).then(([mf, gltf]) => {
    const byId = new Map(mf.organs.map(o => [o.organ_id, o]));
    const group = new THREE.Group();
    const organs = new Map();
    const meshes = [];
    gltf.scene.traverse(o => { if (o.isMesh) meshes.push(o); });
    for (const obj of meshes) {
      const id = keyFromNode(obj.name);
      const meta = byId.get(id);
      if (!meta) continue;
      obj.material = obj.material.clone();
      Object.assign(obj.material, { roughness: 0.9, metalness: 0.0 });
      group.add(obj);
      organs.set(id, { mesh: obj, name: meta.display_name, rgb: meta.rgb });
    }
    // center + scale to a common view height so stage swaps don't jump
    const box = new THREE.Box3().setFromObject(group);
    const c = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const s = VIEW_SIZE / Math.max(size.x, size.y, size.z);
    for (const { mesh } of organs.values()) {
      mesh.position.sub(c);
      mesh.position.multiplyScalar(s);
      mesh.scale.multiplyScalar(s);
    }
    group.visible = false;
    scene.add(group);
    stageData.set(st.id, { group, organs });
    const l = $('loading');
    if (l) l.textContent = `Loaded ${stageData.size}/${STAGES.length} stages (${st.ts}: ${organs.size} organs)…`;
  });
}

Promise.all(STAGES.map(loadStage)).then(() => {
  $('loading').remove();
  buildStageTicks();
  buildOrganGrid();
  // optional deep-link: ?mode=explore&stage=1&organ=16846
  const p = new URLSearchParams(location.search);
  if (p.get('stage')) $('stageSlider').value = p.get('stage');
  if (p.get('organ')) selectedEmapa = 'EMAPA:' + p.get('organ');
  setMode(p.get('mode') === 'explore' ? 'explore' : 'quiz');
}).catch(err => {
  $('loading').textContent = 'Failed to load: ' + (err && err.message ? err.message : err);
  console.error(err);
});

// ---- shared rendering: show one stage, spotlight one organ (or none) ----
let activeStageId = QUIZ_STAGE;

function showStage(id) {
  activeStageId = id;
  for (const [sid, sd] of stageData) sd.group.visible = (sid === id);
  const st = STAGES.find(s => s.id === id);
  $('modelabel').textContent = `${st.ts} · ${st.age} (${st.day}) · mouse embryo`;
}

// spotlight: target organ solid + gently glowing WITH correct depth; rest a translucent
// "jelly" body so you can read where the organ sits. null => whole embryo in colour.
function spotlight(id, emapa) {
  const sd = stageData.get(id);
  if (!sd) return;
  for (const [oid, o] of sd.organs) {
    const m = o.mesh.material;
    const isTarget = emapa && oid === emapa;
    if (emapa == null) {                 // explore, nothing picked: full colour body
      m.vertexColors = true; m.color.setHex(0xffffff);
      m.transparent = true; m.opacity = 0.92; m.depthWrite = true; m.depthTest = true;
      m.emissive.setHex(0x000000); m.emissiveIntensity = 0;
      o.mesh.renderOrder = 0;
    } else if (isTarget) {               // the answer: solid, its colour, glowing, real depth
      m.vertexColors = true; m.color.setHex(0xffffff);
      m.transparent = false; m.opacity = 1; m.depthWrite = true; m.depthTest = true;
      m.emissive.setHex(0x2f7be6); m.emissiveIntensity = 0.5;
      o.mesh.renderOrder = 0;
    } else {                             // context body: translucent grey jelly, drawn after
      m.vertexColors = false; m.color.setHex(0x9aa3b0);
      m.transparent = true; m.opacity = CTX_OPACITY; m.depthWrite = false; m.depthTest = true;
      m.emissive.setHex(0x000000); m.emissiveIntensity = 0;
      o.mesh.renderOrder = 1;           // render translucent skin after the opaque target
    }
    m.needsUpdate = true;
  }
}

// ================= MODES =================
let mode = 'quiz';
function setMode(m) {
  mode = m;
  $('tabQuiz').classList.toggle('active', m === 'quiz');
  $('tabExplore').classList.toggle('active', m === 'explore');
  $('quizPane').classList.toggle('hide', m !== 'quiz');
  $('explorePane').classList.toggle('hide', m !== 'explore');
  controls.autoRotate = true;
  if (m === 'quiz') { showStage(QUIZ_STAGE); startRound(); }
  else { showStage(STAGES[+$('stageSlider').value].id); applyExplore(); }
}
$('tabQuiz').onclick = () => setMode('quiz');
$('tabExplore').onclick = () => setMode('explore');

// ---- QUIZ ----
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [a[i], a[j]] = [a[j], a[i]]; } return a; };
let queue = [], current = null, score = 0, asked = 0;

function startRound() {
  score = 0; asked = 0;
  $('summary').classList.add('hide');
  $('question').classList.remove('hide'); $('choices').classList.remove('hide');
  const organs = stageData.get(QUIZ_STAGE).organs;
  queue = shuffle([...organs.keys()]).slice(0, Math.min(ROUND_SIZE, organs.size));
  $('total').textContent = queue.length; $('score').textContent = '0';
  nextQuestion();
}

function nextQuestion() {
  $('reveal').innerHTML = ''; $('next').hidden = true; $('choices').innerHTML = '';
  controls.autoRotate = true;
  current = queue[asked];
  spotlight(QUIZ_STAGE, current);
  $('question').textContent = `Which organ is highlighted?  (${asked + 1} of ${queue.length})`;
  const organs = stageData.get(QUIZ_STAGE).organs;
  const others = shuffle([...organs.keys()].filter(id => id !== current)).slice(0, 3);
  for (const id of shuffle([current, ...others])) {
    const btn = document.createElement('button');
    btn.className = 'choice'; btn.textContent = organs.get(id).name;
    btn.onclick = () => answer(id, btn);
    $('choices').appendChild(btn);
  }
}

function answer(chosen, btn) {
  controls.autoRotate = false;
  const organs = stageData.get(QUIZ_STAGE).organs;
  const correct = chosen === current;
  if (correct) score++;
  asked++;
  $('score').textContent = String(score);
  for (const b of $('choices').children) {
    b.disabled = true;
    if (b.textContent === organs.get(current).name) b.classList.add('correct');
  }
  if (!correct) btn.classList.add('wrong');
  $('reveal').innerHTML = `<span class="name">${correct ? '✓ ' : '✗ '}${organs.get(current).name}</span><br>${FACTS[current] || ''}`;
  $('next').textContent = asked >= queue.length ? 'See results →' : 'Next organ →';
  $('next').onclick = asked >= queue.length ? showSummary : nextQuestion;
  $('next').hidden = false;
}

function showSummary() {
  $('question').classList.add('hide'); $('choices').classList.add('hide');
  $('reveal').innerHTML = ''; $('next').hidden = true;
  $('summary').classList.remove('hide');
  const pct = Math.round((score / queue.length) * 100);
  $('summaryText').innerHTML = `<h1>${score} / ${queue.length}  (${pct}%)</h1>` +
    `<div class="sub">Nice work — this embryo has hundreds more labelled parts.</div>`;
  spotlight(QUIZ_STAGE, null);
  controls.autoRotate = true;
}
$('restart').onclick = startRound;

// ---- EXPLORE ----
let selectedEmapa = null;
function buildStageTicks() {
  $('stageTicks').innerHTML = STAGES.map(s => `<span>${s.ts}<br>${s.age}</span>`).join('');
}
$('stageSlider').oninput = () => { showStage(STAGES[+$('stageSlider').value].id); applyExplore(); };

function buildOrganGrid() {
  // union of organs across stages, ordered by name
  const union = new Map();
  for (const s of STAGES) for (const [id, o] of stageData.get(s.id).organs)
    if (!union.has(id)) union.set(id, o);
  const grid = $('organGrid'); grid.innerHTML = '';
  for (const [id, o] of [...union].sort((a, b) => a[1].name.localeCompare(b[1].name))) {
    const chip = document.createElement('button');
    chip.className = 'chip'; chip.dataset.id = id;
    const rgb = `rgb(${o.rgb[0]},${o.rgb[1]},${o.rgb[2]})`;
    chip.innerHTML = `<span class="dot" style="background:${rgb}"></span>${o.name}`;
    chip.onclick = () => { selectedEmapa = (selectedEmapa === id ? null : id); applyExplore(); };
    grid.appendChild(chip);
  }
}

function applyExplore() {
  const st = STAGES[+$('stageSlider').value];
  $('stageNow').textContent = st.ts;
  $('stageAge').textContent = `${st.age} · ${st.day}`;
  spotlight(st.id, selectedEmapa);
  for (const chip of $('organGrid').children)
    chip.classList.toggle('active', chip.dataset.id === selectedEmapa);
  const present = selectedEmapa && stageData.get(st.id).organs.has(selectedEmapa);
  if (!selectedEmapa) {
    $('exReveal').innerHTML = '<span class="name">Whole embryo</span><br>Pick an organ to spotlight it across development.';
  } else {
    const anyName = (stageData.get(st.id).organs.get(selectedEmapa) ||
      [...STAGES].map(s => stageData.get(s.id).organs.get(selectedEmapa)).find(Boolean)).name;
    $('exReveal').innerHTML = `<span class="name">${anyName}</span><br>` +
      (present ? (FACTS[selectedEmapa] || '') : `<i>Not delineated at ${st.ts} — slide to another stage.</i>`);
  }
}

// ---- loop ----
addEventListener('resize', () => {
  camera.aspect = view.clientWidth / view.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(view.clientWidth, view.clientHeight);
});
(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();
