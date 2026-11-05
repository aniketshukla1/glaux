// A logo made of light. A swarm of particles orbits as a galaxy, collapses into the mark, holds
// while energy runs along its lines, then bursts back out. Deterministic in the loop position t in
// [0, 1), so the same scene is captured frame by frame for READMEs and runs live on the sites.
import * as THREE from 'three'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'

const TAU = Math.PI * 2
const TEAL = new THREE.Color(0x2dd4bf)
const INDIGO = new THREE.Color(0x818cf8)
const BG = 0x090b10
const V = (x, y, z = 0) => new THREE.Vector3(x, y, z)
const ease = (x) => x * x * (3 - 2 * x)
const clamp01 = (x) => Math.min(1, Math.max(0, x))

function randomizer(seed) {  // mulberry32: the same swarm in every render
  const rnd = () => {
    seed = (seed + 0x6d2b79f5) | 0
    let x = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296
  }
  rnd.gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-9)) * Math.cos(TAU * rnd())
  return rnd
}

// Collects particles (and the star flares that sit on the mark's nodes) for one mark.
class Shape {
  constructor(rnd) {
    this.rnd = rnd
    this.p = []
    this.flares = []
    this.lines = []
    this.loops = []
  }

  add(target, color, { size = 0.024, bright = 1, path = -1, ring = -1, eyeY = -99 } = {}) {
    this.p.push({ target, color, size, bright, path, ring, eyeY })
  }

  // A line of light. `depth` adds fainter echoes behind it, so it has volume when the mark turns.
  beam(a, b, color, { perUnit = 900, width = 0.011, path0 = -1, path1 = -1, depth = true, ring = -1 } = {}) {
    const { rnd } = this
    if (depth) this.lines.push({ a, b, color })
    const n = Math.round(a.distanceTo(b) * perUnit)
    const layers = depth ? [[0, 1, 1], [-0.11, 0.42, 0.5], [-0.22, 0.2, 0.3]] : [[0, 1, 1]]
    for (const [dz, bright, share] of layers) {
      for (let i = 0; i < n * share; i++) {
        const u = rnd()
        const pos = a.clone().lerp(b, u)
        const spread = width * (dz === 0 ? 1 : 2.2)
        pos.x += rnd.gauss() * spread
        pos.y += rnd.gauss() * spread
        pos.z += rnd.gauss() * spread + dz
        this.add(pos, color, {
          size: 0.016 + rnd() * 0.016, bright: bright * (0.7 + rnd() * 0.5),
          path: path0 < 0 ? -1 : path0 + (path1 - path0) * u, ring,
        })
      }
    }
  }

  // A star: a tight cluster of particles plus a flare sprite.
  star(pos, radius, color, { count = 180, flare = 0.24, bright = 1.4, eye = false, ring = -1 } = {}) {
    const { rnd } = this
    for (let i = 0; i < count; i++) {
      const d = V(rnd.gauss(), rnd.gauss(), rnd.gauss()).multiplyScalar(radius * 0.42)
      this.add(pos.clone().add(d), color, {
        size: 0.018 + rnd() * 0.028, bright: bright * (0.6 + rnd() * 0.7), ring, eyeY: eye ? pos.y : -99,
      })
    }
    this.flares.push({ pos: pos.clone(), size: flare, color, eye, ring })
  }
}

// ---- Glaux: the owl, from the exact coordinates in GlauxMark.jsx -------------------------------
function glaux(shape) {
  const P = (x, y, lift = 0) => {
    const nx = (x - 32) / 22
    const ny = -(y - 32) / 22
    return V(nx, ny, 0.34 * (1 - Math.min(1, (nx * nx + ny * ny) / 1.7)) + lift)
  }
  const pt = {
    earL: P(12, 12), earR: P(52, 12), browL: P(21, 24), browR: P(43, 24), bridge: P(32, 29),
    cheekL: P(16, 38), cheekR: P(48, 38), chin: P(32, 52),
  }
  // Two signed hand-offs race along these chains while the mark holds.
  for (const chain of [
    [pt.earL, pt.browL, pt.bridge, pt.browR, pt.earR],
    [pt.browL, pt.cheekL, pt.chin, pt.cheekR, pt.browR],
  ]) {
    const lens = chain.slice(1).map((p, i) => p.distanceTo(chain[i]))
    const total = lens.reduce((a, b) => a + b)
    let at = 0
    lens.forEach((len, i) => {
      shape.beam(chain[i], chain[i + 1], TEAL, { path0: at / total, path1: (at + len) / total })
      at += len
    })
  }
  Object.values(pt).forEach((p) => shape.star(p, 0.12, TEAL))
  for (const eye of [P(25, 37, 0.1), P(39, 37, 0.1)]) {
    shape.star(eye, 0.2, INDIGO, { count: 720, flare: 0.44, bright: 1.3, eye: true })
  }
  return { palette: [TEAL, INDIGO], sway: 0.42, tilt: 0, blink: true, ringSpeeds: [] }
}

// ---- AthenaDB: the store. Three rings of vectors stacked into a database ------------------------
function athenadb(shape) {
  const R = 1.0
  const levels = [0.62, 0, -0.62]
  const N = 10
  levels.forEach((y, ring) => {
    shape.loops.push({ y, radius: R, color: INDIGO })
    for (let i = 0; i < 120; i++) {
      const a = (i / 120) * TAU
      const b = ((i + 1) / 120) * TAU
      shape.beam(V(Math.cos(a) * R, y, Math.sin(a) * R), V(Math.cos(b) * R, y, Math.sin(b) * R), INDIGO, {
        perUnit: 330, width: 0.009, depth: false, ring,
      })
    }
    for (let i = 0; i < N; i++) {
      const a = (i / N) * TAU
      const lit = (i + ring * 3) % N === 0
      shape.star(V(Math.cos(a) * R, y, Math.sin(a) * R), lit ? 0.13 : 0.07, lit ? TEAL : INDIGO, {
        count: lit ? 170 : 60, flare: lit ? 0.24 : 0.09, ring,
      })
    }
    // the stored vectors: a faint spiral across each disc
    for (let i = 0; i < 420; i++) {
      const r = R * Math.sqrt(shape.rnd()) * 0.97
      const a = shape.rnd() * TAU
      shape.add(V(Math.cos(a) * r, y + shape.rnd.gauss() * 0.008, Math.sin(a) * r), INDIGO, {
        size: 0.012 + shape.rnd() * 0.012, bright: 0.4, ring,
      })
    }
  })
  shape.beam(V(0, 0.68, 0), V(0, -0.68, 0), TEAL, { perUnit: 700, width: 0.008, depth: false, path0: 0, path1: 1 })
  shape.lines.push({ a: V(0, 0.68, 0), b: V(0, -0.68, 0), color: TEAL })
  shape.star(V(0, 0, 0), 0.17, TEAL, { count: 560, flare: 0.44, bright: 1.3 })
  return { palette: [INDIGO, TEAL], sway: 0.28, tilt: 0.52, blink: false, ringSpeeds: [3 / N, -2 / N, 3 / N] }
}

const MARKS = { glaux, athenadb }

// The swarm's resting shape: a tilted two-armed galaxy around the mark.
function galaxyPoint(rnd, radius) {
  const r = radius * (0.06 + 0.94 * rnd() ** 0.8)
  const arm = rnd() < 0.5 ? 0 : Math.PI
  const a = arm + (r / radius) * 5.2 + rnd.gauss() * (0.1 + 0.16 * r / radius)
  const h = rnd.gauss() * (0.03 + 0.12 * (1 - r / radius))
  const p = V(Math.cos(a) * r, h, Math.sin(a) * r)
  p.applyEuler(new THREE.Euler(1.02, 0, -0.34))
  return p
}

const vertex = /* glsl */`
  attribute vec3 aTarget;
  attribute vec3 aSwarm;
  attribute vec3 aColor;
  attribute float aSeed;
  attribute float aSize;
  attribute float aBright;
  attribute float aPath;
  attribute float aRing;
  attribute float aEyeY;
  uniform float uForm, uTurn, uLoop, uPulse, uFlare, uBlink, uPx;
  uniform vec3 uRingTurn;
  uniform mat4 uBody;
  varying vec3 vColor;
  varying float vGain;

  vec3 rotY(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(c*p.x + s*p.z, p.y, -s*p.x + c*p.z); }

  void main() {
    float m = clamp((uForm - aSeed * 0.42) / 0.58, 0.0, 1.0);
    m = m * m * (3.0 - 2.0 * m);

    vec3 g = rotY(aSwarm, uTurn * floor(1.0 + aSeed * 1.999));
    vec3 f = aTarget;
    if (aEyeY > -90.0) f.y = aEyeY + (f.y - aEyeY) * uBlink;
    if (aRing >= 0.0) f = rotY(f, uRingTurn[int(aRing)]);
    f = (uBody * vec4(f, 1.0)).xyz;
    f += 0.006 * vec3(sin(uLoop * 3.0 + aSeed * 91.0), sin(uLoop * 2.0 + aSeed * 37.0), cos(uLoop * 2.0 + aSeed * 53.0));

    vec3 p = mix(g, f, m);
    float arc = sin(3.14159 * m);                   // curved flight, not a straight line
    vec3 side = normalize(cross(f - g + vec3(1e-3), vec3(0.0, 1.0, 0.0)) + vec3(1e-3));
    p += side * arc * (0.35 + aSeed * 0.75);
    p.y += arc * 0.3 * sin(aSeed * 41.0);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    float pulse = 0.0;
    if (aPath >= 0.0 && uPulse >= 0.0) { float d = (aPath - uPulse) / 0.05; pulse = exp(-d * d) * m; }
    float settled = smoothstep(0.92, 1.0, m);
    vGain = mix(0.95, aBright, settled) * (1.0 + 2.4 * pulse + 0.5 * uFlare * settled) + arc * 0.3;
    vColor = aColor + vec3(0.65) * pulse;
    gl_PointSize = aSize * mix(1.65, 1.0, m) * (1.0 + 0.9 * pulse) * uPx / -mv.z;
  }
`

const fragment = /* glsl */`
  varying vec3 vColor;
  varying float vGain;
  void main() {
    float d = length(gl_PointCoord - 0.5) * 2.0;
    if (d > 1.0) discard;
    float a = pow(1.0 - d, 2.3);
    gl_FragColor = vec4(vColor * a * vGain, a);
  }
`

function flareTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 256
  const g = c.getContext('2d')
  const core = g.createRadialGradient(128, 128, 0, 128, 128, 128)
  core.addColorStop(0, 'rgba(255,255,255,1)')
  core.addColorStop(0.08, 'rgba(255,255,255,.55)')
  core.addColorStop(0.3, 'rgba(255,255,255,.09)')
  core.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = core
  g.fillRect(0, 0, 256, 256)
  g.globalCompositeOperation = 'lighter'
  for (const [w, h] of [[128, 1.5], [1.5, 128]]) {  // a four-point star
    const streak = w > h ? g.createLinearGradient(0, 128, 256, 128) : g.createLinearGradient(128, 0, 128, 256)
    streak.addColorStop(0, 'rgba(255,255,255,0)')
    streak.addColorStop(0.5, 'rgba(255,255,255,.5)')
    streak.addColorStop(1, 'rgba(255,255,255,0)')
    g.fillStyle = streak
    g.fillRect(128 - w, 128 - h, w * 2, h * 2)
  }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

function formAt(t) {
  if (t < 0.34) return 1
  if (t < 0.52) return 1 - ease((t - 0.34) / 0.18)
  if (t < 0.6) return 0
  if (t < 0.9) return ease((t - 0.6) / 0.3)
  return 1
}

export function createSwarmLogo({
  canvas, mark = 'glaux', distance = 7, offsetX = 0, offsetY = 0, scale = 1, galaxy = 2.25,
  density = 1, bloom = true, dust = 900, background = BG, capture = false,
}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: capture, powerPreference: 'high-performance' })
  renderer.setClearColor(background, 1)
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(background)
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 60)
  camera.position.z = distance

  const stage = new THREE.Group()
  stage.scale.setScalar(scale)
  scene.add(stage)
  const body = new THREE.Group()
  stage.add(body)

  const rnd = randomizer(11)
  const shape = new Shape(rnd)
  const info = MARKS[mark](shape)

  // Thin the particles evenly on smaller devices; the mark's proportions don't change.
  const keep = density >= 1 ? shape.p : shape.p.filter(() => rnd() < density)
  const n = keep.length
  const arr = (size) => new Float32Array(n * size)
  const aTarget = arr(3), aSwarm = arr(3), aColor = arr(3)
  const aSeed = arr(1), aSize = arr(1), aBright = arr(1), aPath = arr(1), aRing = arr(1), aEyeY = arr(1)
  keep.forEach((q, i) => {
    q.target.toArray(aTarget, i * 3)
    galaxyPoint(rnd, galaxy).toArray(aSwarm, i * 3)
    q.color.toArray(aColor, i * 3)
    aSeed[i] = rnd()
    aSize[i] = q.size / Math.sqrt(Math.max(density, 0.25))
    aBright[i] = q.bright
    aPath[i] = q.path
    aRing[i] = q.ring
    aEyeY[i] = q.eyeY
  })
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(aTarget, 3))
  geo.setAttribute('aTarget', new THREE.BufferAttribute(aTarget, 3))
  geo.setAttribute('aSwarm', new THREE.BufferAttribute(aSwarm, 3))
  geo.setAttribute('aColor', new THREE.BufferAttribute(aColor, 3))
  geo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1))
  geo.setAttribute('aSize', new THREE.BufferAttribute(aSize, 1))
  geo.setAttribute('aBright', new THREE.BufferAttribute(aBright, 1))
  geo.setAttribute('aPath', new THREE.BufferAttribute(aPath, 1))
  geo.setAttribute('aRing', new THREE.BufferAttribute(aRing, 1))
  geo.setAttribute('aEyeY', new THREE.BufferAttribute(aEyeY, 1))
  const uniforms = {
    uForm: { value: 1 }, uTurn: { value: 0 }, uLoop: { value: 0 }, uPulse: { value: -1 }, uFlare: { value: 0 },
    uBlink: { value: 1 }, uPx: { value: 1 }, uRingTurn: { value: V(0, 0, 0) }, uBody: { value: new THREE.Matrix4() },
  }
  const swarm = new THREE.Points(geo, new THREE.ShaderMaterial({
    uniforms, vertexShader: vertex, fragmentShader: fragment,
    blending: THREE.AdditiveBlending, transparent: true, depthTest: false, depthWrite: false,
  }))
  swarm.frustumCulled = false
  stage.add(swarm)

  // Star flares ride on the same transforms as the particles under them.
  const tex = flareTexture()
  const ringGroups = info.ringSpeeds.map(() => {
    const g = new THREE.Group()
    body.add(g)
    return g
  })
  const flares = shape.flares.map((f) => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, color: f.color, transparent: true, blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false, opacity: 0,
    }))
    s.position.copy(f.pos)
    s.scale.setScalar(f.size * 2)
    ;(f.ring >= 0 ? ringGroups[f.ring] : body).add(s)
    return { sprite: s, ...f }
  })

  const glowMat = (color) => new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false,
  })
  const cores = shape.lines.map(({ a, b, color }) => {
    const d = b.clone().sub(a)
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.0085, 0.0085, d.length(), 8, 1, true), glowMat(color))
    m.position.copy(a).addScaledVector(d, 0.5)
    m.quaternion.setFromUnitVectors(V(0, 1, 0), d.normalize())
    body.add(m)
    return m
  })
  shape.loops.forEach(({ y, radius, color }) => {
    const m = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.0075, 8, 160), glowMat(color))
    m.rotation.x = Math.PI / 2
    m.position.y = y
    body.add(m)
    cores.push(m)
  })

  // Far dust gives the frame depth; it drifts opposite to the mark.
  const dustRnd = randomizer(5)
  const dustPos = new Float32Array(dust * 3)
  const dustCol = new Float32Array(dust * 3)
  for (let i = 0; i < dust; i++) {
    V((dustRnd() - 0.5) * 22, (dustRnd() - 0.5) * 9, -7 + dustRnd() * 6).toArray(dustPos, i * 3)
    ;(i % 3 === 0 ? info.palette[1] : info.palette[0]).clone().multiplyScalar(0.25 + dustRnd() * 0.5).toArray(dustCol, i * 3)
  }
  const dg = new THREE.BufferGeometry()
  dg.setAttribute('position', new THREE.BufferAttribute(dustPos, 3))
  dg.setAttribute('color', new THREE.BufferAttribute(dustCol, 3))
  const dotCanvas = document.createElement('canvas')
  dotCanvas.width = dotCanvas.height = 32
  const dc = dotCanvas.getContext('2d')
  const rg = dc.createRadialGradient(16, 16, 0, 16, 16, 16)
  rg.addColorStop(0, 'rgba(255,255,255,1)')
  rg.addColorStop(1, 'rgba(255,255,255,0)')
  dc.fillStyle = rg
  dc.fillRect(0, 0, 32, 32)
  const dustField = new THREE.Points(dg, new THREE.PointsMaterial({
    size: 0.06, vertexColors: true, map: new THREE.CanvasTexture(dotCanvas), transparent: true,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }))
  scene.add(dustField)

  let composer = null
  let bloomPass = null
  if (bloom) {
    composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(4, 4, { type: THREE.HalfFloatType }))
    composer.addPass(new RenderPass(scene, camera))
    bloomPass = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.3, 0.5, 0.22)
    composer.addPass(bloomPass)
    composer.addPass(new OutputPass())
  }

  let height = 1
  let useBloom = bloom
  return {
    particles: n,
    // Live pages turn this off when a device can't keep up; particles still render.
    setBloom(on) {
      useBloom = on && bloom
    },
    resize(w, h, dpr = 1) {
      height = h * dpr
      renderer.setPixelRatio(dpr)
      renderer.setSize(w, h, false)
      if (composer) {
        composer.setPixelRatio(dpr)
        composer.setSize(w, h)
      }
      camera.aspect = w / h
      // A lens shift, not a moved object: the mark stays upright wherever it sits in the frame.
      const unit = h / (2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
      camera.setViewOffset(w, h, -offsetX * unit, offsetY * unit, w, h)
      uniforms.uPx.value = height / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
    },
    // t: loop position in [0, 1). tilt: pointer parallax for the live version.
    render(t, tilt = { x: 0, y: 0 }) {
      const u = uniforms
      u.uLoop.value = TAU * t
      u.uForm.value = formAt(t)
      u.uTurn.value = TAU * t
      u.uFlare.value = Math.exp(-(((t - 0.905) / 0.022) ** 2))
      const hold = (t + 0.08) % 1  // the pulse runs from just before the mark settles
      u.uPulse.value = hold < 0.4 ? hold / 0.4 : -1
      const dBlink = Math.abs(t - 0.24)
      u.uBlink.value = info.blink && dBlink < 0.016 ? 0.06 + 0.94 * (dBlink / 0.016) ** 2 : 1

      body.rotation.set(info.tilt + 0.07 * Math.sin(TAU * t * 2 + 0.6), info.sway * Math.sin(TAU * t), 0)
      body.position.y = 0.03 * Math.sin(TAU * t)
      body.updateMatrix()
      u.uBody.value.copy(body.matrix)
      info.ringSpeeds.forEach((sp, i) => {
        const a = TAU * sp * t
        u.uRingTurn.value.setComponent(i, a)
        ringGroups[i].rotation.y = a
      })
      stage.rotation.y = tilt.x
      stage.rotation.x = tilt.y
      dustField.rotation.y = 0.018 * Math.sin(TAU * t) - tilt.x * 0.15
      dustField.rotation.x = 0.006 * Math.cos(TAU * t) - tilt.y * 0.15

      const lit = clamp01((u.uForm.value - 0.82) / 0.18)
      cores.forEach((m) => { m.material.opacity = lit * 0.85 })
      flares.forEach((f) => {
        const blink = f.eye ? u.uBlink.value : 1
        f.sprite.material.opacity = lit * blink * (0.8 + 0.2 * Math.sin(TAU * t * 3 + f.size * 40) + 0.45 * u.uFlare.value)
        f.sprite.scale.set(f.size * 2, f.size * 2 * (f.eye ? Math.max(blink, 0.3) : 1), 1)
      })

      if (useBloom) composer.render()
      else renderer.render(scene, camera)
    },
    dispose() {
      composer?.dispose()
      renderer.dispose()
    },
  }
}
