import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const STAGE = 'ts26';
const ROUND_SIZE = 10;          // organs asked per round
const DIM_OPACITY = 0.12;       // non-target organs fade to a faint context silhouette

// Short, classroom-friendly facts keyed by EMAPA organ id.
const FACTS = {
  'EMAPA:16846': 'The liver — at this stage it is the main site of blood-cell production, not just digestion.',
  'EMAPA:16688': 'A heart atrium — the two atria receive blood returning to the heart.',
  'EMAPA:17331': 'The heart ventricle — the muscular pump that pushes blood out to the body and lungs.',
  'EMAPA:16728': 'The lung — still fluid-filled in the embryo; it only inflates with air at birth.',
  'EMAPA:17373': 'The metanephros — the embryonic kidney that becomes the adult kidney.',
  'EMAPA:17021': 'The stomach — a muscular bag that begins the breakdown of food.',
  'EMAPA:17185': 'The tongue — packed with muscle; one of the most muscular organs for its size.',
  'EMAPA:19143': 'The femur — the thigh bone, forming here through cartilage before it ossifies.',
  'EMAPA:19106': 'The humerus — the upper-arm/forelimb bone.',
  'EMAPA:16895': 'The forebrain — becomes the cerebral hemispheres, the thinking part of the brain.',
  'EMAPA:16974': 'The midbrain — relays vision, hearing and movement signals.',
  'EMAPA:16916': 'The hindbrain — gives rise to the cerebellum and brainstem controlling balance and breathing.',
  'EMAPA:17577': 'The spinal cord — the neural cable linking brain and body.',
  'EMAPA:18768': 'The thymus — where T-cells of the immune system mature; largest early in life.',
  'EMAPA:18767': 'The spleen — filters blood and supports the immune system.',
  'EMAPA:17503': 'The pancreas — makes both digestive enzymes and insulin.',
  'EMAPA:18321': 'The bladder — stores urine produced by the kidneys.',
  'EMAPA:17701': 'The diaphragm — the dome-shaped muscle that drives breathing.',
  'EMAPA:17838': 'The lens of the eye — a transparent disc that focuses light onto the retina.',
  'EMAPA:18010': 'A rib — part of the cage protecting the heart and lungs.',
};

const view = document.getElementById('view');
const scoreEl = document.getElementById('score');
const totalEl = document.getElementById('total');
const questionEl = document.getElementById('question');
const choicesEl = document.getElementById('choices');
const revealEl = document.getElementById('reveal');
const nextBtn = document.getElementById('next');
const restartBtn = document.getElementById('restart');
const quizEl = document.getElementById('quiz');
const summaryEl = document.getElementById('summary');
const summaryTextEl = document.getElementById('summaryText');

// ---- three.js scene ----
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(view.clientWidth, view.clientHeight);
view.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(45, view.clientWidth / view.clientHeight, 1, 5000);
camera.position.set(0, 0, 1400);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.6;

scene.add(new THREE.HemisphereLight(0xffffff, 0x444455, 1.1));
const key = new THREE.DirectionalLight(0xffffff, 1.4);
key.position.set(1, 1, 1.5);
scene.add(key);
const fill = new THREE.DirectionalLight(0xffffff, 0.6);
fill.position.set(-1, -0.5, -1);
scene.add(fill);

const root = new THREE.Group();
scene.add(root);

const organs = new Map();   // organ_id -> { mesh, name, baseColor }
let manifest = null;
let modelRadius = 500;

function keyFromNode(nodeName) {
  // GLB node "EMAPA16688" -> manifest id "EMAPA:16688"
  return nodeName.replace(/^EMAPA/, 'EMAPA:');
}

Promise.all([
  fetch(`./data/${STAGE}.json`).then(r => r.json()),
  new Promise((res, rej) => new GLTFLoader().load(`./data/${STAGE}.glb`, res, undefined, rej)),
]).then(([mf, gltf]) => {
  manifest = mf;
  const byId = new Map(mf.organs.map(o => [o.organ_id, o]));

  // Collect meshes first — do NOT reparent inside traverse(), which would mutate
  // the child array mid-iteration and corrupt the traversal.
  const meshes = [];
  gltf.scene.traverse(obj => { if (obj.isMesh) meshes.push(obj); });

  for (const obj of meshes) {
    const id = keyFromNode(obj.name);
    const meta = byId.get(id);
    if (!meta) continue;
    obj.material = obj.material.clone();   // independent material per organ
    const mat = obj.material;
    mat.vertexColors = true;
    mat.roughness = 0.85;
    mat.metalness = 0.0;
    mat.transparent = true;
    mat.emissive = new THREE.Color(0x000000);
    root.add(obj);
    organs.set(id, { mesh: obj, name: meta.display_name, baseColor: meta.rgb });
  }

  // center the model and frame it
  const box = new THREE.Box3().setFromObject(root);
  const center = box.getCenter(new THREE.Vector3());
  root.position.sub(center);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  modelRadius = sphere.radius;
  camera.position.set(0, 0, modelRadius * 2.6);
  controls.target.set(0, 0, 0);
  controls.update();

  document.getElementById('loading').remove();
  startRound();
}).catch(err => {
  const el = document.getElementById('loading');
  if (el) el.textContent = 'ERR: ' + (err && err.stack ? err.stack : err);
  console.error(err);
});

// ---- quiz state ----
let queue = [];
let current = null;
let score = 0;
let asked = 0;

function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [a[i], a[j]] = [a[j], a[i]]; } return a; }

function startRound() {
  score = 0; asked = 0;
  summaryEl.classList.remove('show');
  quizEl.classList.remove('hide');
  queue = shuffle([...organs.keys()]).slice(0, Math.min(ROUND_SIZE, organs.size));
  totalEl.textContent = queue.length;
  scoreEl.textContent = '0';
  nextQuestion();
}

function nextQuestion() {
  revealEl.innerHTML = '';
  nextBtn.hidden = true;
  choicesEl.innerHTML = '';
  controls.autoRotate = true;

  current = queue[asked];

  // Target: solid, its own colour, glowing. Others: one uniform faint grey ghost
  // so the whole embryo reads as a single body and the target clearly pops.
  for (const [id, o] of organs) {
    const isTarget = id === current;
    const m = o.mesh.material;
    if (isTarget) {
      m.vertexColors = true;            // show the organ's real colour
      m.color.setHex(0xffffff);
      m.transparent = false;
      m.opacity = 1.0;
      m.depthWrite = true;
      m.depthTest = false;              // glow *through* the body so it's never hidden
      m.emissive.setHex(0x1d5fd0);
      m.emissiveIntensity = 0.55;
      o.mesh.renderOrder = 10;
    } else {
      m.vertexColors = false;           // flat grey ghost, not rainbow murk
      m.color.setHex(0x8a93a0);
      m.transparent = true;
      m.opacity = DIM_OPACITY;
      m.depthWrite = false;
      m.depthTest = true;
      m.emissive.setHex(0x000000);
      m.emissiveIntensity = 0.0;
      o.mesh.renderOrder = 0;
    }
    m.needsUpdate = true;
  }

  questionEl.textContent = `Which organ is highlighted? (${asked + 1} of ${queue.length})`;

  // build 4 choices: the answer + 3 distractors
  const others = shuffle([...organs.keys()].filter(id => id !== current)).slice(0, 3);
  const options = shuffle([current, ...others]);
  for (const id of options) {
    const btn = document.createElement('button');
    btn.className = 'choice';
    btn.textContent = organs.get(id).name;
    btn.onclick = () => answer(id, btn);
    choicesEl.appendChild(btn);
  }
}

function answer(chosenId, btn) {
  controls.autoRotate = false;
  const correct = chosenId === current;
  if (correct) score++;
  asked++;
  scoreEl.textContent = String(score);

  for (const b of choicesEl.children) {
    b.disabled = true;
    if (b.textContent === organs.get(current).name) b.classList.add('correct');
  }
  if (!correct) btn.classList.add('wrong');

  const target = organs.get(current);
  const fact = FACTS[current] || '';
  revealEl.innerHTML = `<span class="name">${correct ? '✓ ' : '✗ '}${target.name}</span><br>${fact}`;

  if (asked >= queue.length) {
    nextBtn.textContent = 'See results →';
    nextBtn.onclick = showSummary;
  } else {
    nextBtn.textContent = 'Next organ →';
    nextBtn.onclick = nextQuestion;
  }
  nextBtn.hidden = false;
}

function showSummary() {
  quizEl.classList.add('hide');
  summaryEl.classList.add('show');
  const pct = Math.round((score / queue.length) * 100);
  summaryTextEl.innerHTML =
    `<h1>${score} / ${queue.length} correct (${pct}%)</h1>` +
    `<div class="sub">Nice work — the mouse embryo has hundreds more labelled parts.</div>`;
  // reveal the whole embryo again in full colour
  for (const [, o] of organs) {
    const m = o.mesh.material;
    m.vertexColors = true;
    m.color.setHex(0xffffff);
    m.transparent = true;
    m.opacity = 0.9;
    m.depthWrite = true;
    m.depthTest = true;
    m.emissive.setHex(0x000000);
    m.emissiveIntensity = 0.0;
    o.mesh.renderOrder = 0;
    m.needsUpdate = true;
  }
  controls.target.set(0, 0, 0);
  controls.autoRotate = true;
}
restartBtn.onclick = startRound;

// ---- render loop ----
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
