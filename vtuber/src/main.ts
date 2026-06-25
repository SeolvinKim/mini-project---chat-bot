import './style.css'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { speech, emotion, initChat } from './chat'

const DEFAULT_VRM_URL = `${import.meta.env.BASE_URL}AvatarSample_Q.vrm`

const statusEl = document.getElementById('status') as HTMLDivElement
const canvasEl = document.getElementById('three') as HTMLCanvasElement
const stageEl = document.getElementById('stage') as HTMLDivElement

const setStatus = (text: string) => (statusEl.textContent = text)

// ---------------------------------------------------------------------------
// three.js 씬
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ canvas: canvasEl, alpha: true, antialias: true })
renderer.setPixelRatio(window.devicePixelRatio)
renderer.setSize(stageEl.clientWidth, stageEl.clientHeight)

const scene = new THREE.Scene()

const camera = new THREE.PerspectiveCamera(30, stageEl.clientWidth / stageEl.clientHeight, 0.1, 20)
camera.position.set(0, 1.35, 1.5)

const controls = new OrbitControls(camera, renderer.domElement)
controls.target.set(0, 1.3, 0)
controls.update()

const light = new THREE.DirectionalLight(0xffffff, 1.6)
light.position.set(1, 1.5, 1.2).normalize()
scene.add(light)
scene.add(new THREE.AmbientLight(0xffffff, 0.7))

window.addEventListener('resize', () => {
  camera.aspect = stageEl.clientWidth / stageEl.clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(stageEl.clientWidth, stageEl.clientHeight)
})

// ---------------------------------------------------------------------------
// VRM 로딩
// ---------------------------------------------------------------------------
type BoneName = Parameters<NonNullable<VRM['humanoid']>['getNormalizedBoneNode']>[0]

let currentVrm: VRM | null = null
const gltfLoader = new GLTFLoader()
gltfLoader.register((parser) => new VRMLoaderPlugin(parser))

function loadVRM(url: string) {
  setStatus('VRM 불러오는 중…')
  gltfLoader.load(
    url,
    (gltf) => {
      const vrm = gltf.userData.vrm as VRM
      if (currentVrm) {
        scene.remove(currentVrm.scene)
        VRMUtils.deepDispose(currentVrm.scene)
      }
      VRMUtils.removeUnnecessaryVertices(gltf.scene)
      VRMUtils.combineSkeletons(gltf.scene)
      VRMUtils.rotateVRM0(vrm)
      vrm.scene.traverse((obj) => ((obj as THREE.Mesh).frustumCulled = false))
      if (vrm.lookAt) vrm.lookAt.target = undefined
      currentVrm = vrm
      scene.add(vrm.scene)
      ;(window as Window & { __vrm?: VRM }).__vrm = vrm
      const exprs = vrm.expressionManager?.expressions.map((e) => e.expressionName) ?? []
      setStatus('준비됐어요! 아래에 말을 걸어보세요.')
      console.log('[VRM] loaded:', { url, expressions: exprs })
    },
    undefined,
    (err) => {
      console.error(err)
      setStatus('VRM 로드 실패')
    },
  )
}

// ---------------------------------------------------------------------------
// 리깅 헬퍼
// ---------------------------------------------------------------------------
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
type XYZ = { x: number; y: number; z: number }

function rigRotation(name: BoneName, rot: XYZ, dampener = 1, lerpAmount = 0.3) {
  const bone = currentVrm?.humanoid.getNormalizedBoneNode(name)
  if (!bone) return
  const euler = new THREE.Euler(rot.x * dampener, rot.y * dampener, rot.z * dampener, 'XYZ')
  bone.quaternion.slerp(new THREE.Quaternion().setFromEuler(euler), lerpAmount)
}

function setExpr(name: string, value: number, smoothing = 0.4) {
  const em = currentVrm?.expressionManager
  if (!em || !em.getExpression(name)) return
  em.setValue(name, lerp(em.getValue(name) ?? 0, value, smoothing))
}

// ---------------------------------------------------------------------------
// 아이들 모션 (웹캠 없이 항상 실행)
// ---------------------------------------------------------------------------
const REST_ARM_Z = 1.18
let nextBlinkAt = 0
let blinkUntil = 0
let nextSmileAt = 0
let smileUntil = 0
let emotionUntil = 0

function idleAnimate() {
  if (!currentVrm) return
  const t = performance.now() / 1000
  const now = performance.now()
  const talk = speech.speaking ? 1.8 : 1

  const breath = Math.sin(t * 1.1) * 0.02
  rigRotation('spine', { x: breath, y: Math.sin(t * 0.33) * 0.02, z: 0 }, 1, 0.08)
  rigRotation('chest', { x: breath * 0.6, y: 0, z: 0 }, 1, 0.08)

  rigRotation(
    'neck',
    {
      x: Math.sin(t * 1.3) * 0.03 * talk + (speech.speaking ? Math.sin(t * 5) * 0.05 : 0),
      y: Math.sin(t * 0.5) * 0.12 * talk,
      z: Math.sin(t * 0.4) * 0.03,
    },
    1,
    0.1,
  )

  rigRotation('hips', { x: 0, y: Math.sin(t * 0.27) * 0.04, z: Math.sin(t * 0.6) * 0.015 }, 1, 0.05)

  const armSway = Math.sin(t * 0.8) * 0.04
  rigRotation('leftUpperArm', { x: 0.05, y: 0, z: -REST_ARM_Z - armSway }, 1, 0.06)
  rigRotation('rightUpperArm', { x: 0.05, y: 0, z: REST_ARM_Z + armSway }, 1, 0.06)
  rigRotation('leftLowerArm', { x: 0, y: -0.25, z: -0.1 }, 1, 0.06)
  rigRotation('rightLowerArm', { x: 0, y: 0.25, z: 0.1 }, 1, 0.06)

  if (currentVrm.lookAt) {
    currentVrm.lookAt.yaw = Math.sin(t * 0.3) * 9
    currentVrm.lookAt.pitch = Math.sin(t * 0.22) * 4
  }

  if (now > nextBlinkAt) {
    blinkUntil = now + 120
    nextBlinkAt = now + 2500 + Math.random() * 3500
  }
  setExpr('blink', now < blinkUntil ? 1 : 0, 0.5)

  if (now > nextSmileAt) {
    smileUntil = now + 2000 + Math.random() * 2000
    nextSmileAt = now + 15000 + Math.random() * 20000
  }
  if (now > emotionUntil) {
    const smileVal = now < smileUntil ? 0.35 : 0
    setExpr('happy', smileVal, 0.05)
    setExpr('joy', smileVal, 0.05)
  }
}

// ---------------------------------------------------------------------------
// TTS 립싱크
// ---------------------------------------------------------------------------
function applyMouth() {
  if (!currentVrm) return
  if (speech.speaking) {
    setExpr('aa', Math.min(1, speech.mouthOpen), 0.3)
    setExpr('ih', 0, 0.5)
    setExpr('ou', 0, 0.5)
    setExpr('ee', 0, 0.5)
    setExpr('oh', 0, 0.5)
  } else {
    setExpr('aa', 0, 0.3)
  }
}

// ---------------------------------------------------------------------------
// 봇 감정 표정
// ---------------------------------------------------------------------------
const EMOTION_MAP: Record<string, string[]> = {
  happy: ['happy', 'joy'],
  sad: ['sad', 'sorrow'],
  surprised: ['surprised', 'fun'],
}
const ALL_EMOTION_EXPRS = ['happy', 'joy', 'sad', 'sorrow', 'surprised', 'fun', 'relaxed', 'angry']

function applyEmotion() {
  if (!currentVrm) return
  const now = performance.now()

  if (emotion.name) {
    emotionUntil = now + 4000
    const targets = EMOTION_MAP[emotion.name] ?? [emotion.name]
    for (const e of ALL_EMOTION_EXPRS) {
      setExpr(e, targets.includes(e) ? emotion.intensity : 0, 0.08)
    }
    emotion.name = ''
  } else if (now > emotionUntil + 1000) {
    for (const e of ALL_EMOTION_EXPRS) setExpr(e, 0, 0.04)
  }
}

// ---------------------------------------------------------------------------
// 메인 루프
// ---------------------------------------------------------------------------
const clock = new THREE.Clock()

function animate() {
  requestAnimationFrame(animate)
  idleAnimate()
  applyEmotion()
  applyMouth()
  if (currentVrm) currentVrm.update(clock.getDelta())
  renderer.render(scene, camera)
}

// ---------------------------------------------------------------------------
initChat()
loadVRM(DEFAULT_VRM_URL)
animate()
