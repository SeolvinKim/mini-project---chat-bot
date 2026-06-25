import './style.css'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRM, VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { HolisticLandmarker, FilesetResolver } from '@mediapipe/tasks-vision'
import * as Kalidokit from 'kalidokit'
import { speech, emotion, initChat } from './chat'

// ---------------------------------------------------------------------------
// 설정 (라이브로 튜닝할 값들)
// ---------------------------------------------------------------------------
const SETTINGS = {
  // 좌우가 거꾸로면 true 로 바꿔서 머리/눈/손을 미러링
  mirror: false,
  // 엉덩이 위치(상하좌우 이동)까지 반영할지. 책상 웹캠이면 보통 꺼두는 게 안정적
  applyHipsPosition: false,
  // 눈동자 최대 각도(도)
  pupilRange: 28,
  // 화면에 추적 수치 오버레이 표시 (진단용)
  debug: true,
}

// 팔 출력 보정 (입력 랜드마크는 GitHub 원본 그대로 raw). 키 q/w/e=축부호, r=좌우스왑
const armFix = { x: 1, y: 1, z: 1, swap: false }
window.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase()
  if (k === 'q') armFix.x *= -1
  else if (k === 'w') armFix.y *= -1
  else if (k === 'e') armFix.z *= -1
  else if (k === 'r') armFix.swap = !armFix.swap
})

// 내 모델 (public/avatar.vrm). 다른 모델은 HUD의 'VRM 불러오기'로 교체 가능
const DEFAULT_VRM_URL = `${import.meta.env.BASE_URL}AvatarSample_Q.vrm`

const statusEl = document.getElementById('status') as HTMLDivElement
const videoEl = document.getElementById('video') as HTMLVideoElement
const canvasEl = document.getElementById('three') as HTMLCanvasElement
// 렌더 영역은 전체 창이 아니라 왼쪽 '무대'(채팅 패널을 뺀 영역) 크기를 따른다.
const stageEl = document.getElementById('stage') as HTMLDivElement
const vrmFileEl = document.getElementById('vrm-file') as HTMLInputElement
const camBtn = document.getElementById('cam-btn') as HTMLButtonElement

const setStatus = (text: string) => (statusEl.textContent = text)

// 진단용 오버레이
const dbgEl = document.createElement('pre')
dbgEl.style.cssText =
  'position:fixed;left:16px;top:64px;margin:0;padding:10px 14px;background:rgba(0,0,0,.7);' +
  'color:#3f6;font:13px/1.6 monospace;white-space:pre;border-radius:8px;z-index:20;pointer-events:none'
dbgEl.style.display = SETTINGS.debug ? 'block' : 'none'
document.body.appendChild(dbgEl)

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
      // VRM 0.0 모델은 -Z를 향하므로 정면(+Z)으로 회전
      VRMUtils.rotateVRM0(vrm)
      vrm.scene.traverse((obj) => ((obj as THREE.Mesh).frustumCulled = false))
      // lookAt 를 수동(yaw/pitch)으로 제어하기 위해 타깃 해제
      if (vrm.lookAt) vrm.lookAt.target = undefined
      currentVrm = vrm
      scene.add(vrm.scene)
      ;(window as Window & { __vrm?: VRM }).__vrm = vrm
      const exprs = vrm.expressionManager?.expressions.map((e) => e.expressionName) ?? []
      console.log('[VRM] loaded:', {
        url,
        meta: vrm.meta,
        hasHumanoid: !!vrm.humanoid,
        expressions: exprs,
      })
      setStatus(`VRM 로드 완료 (표정 ${exprs.length}종). 아래에 말을 걸어보세요 — 웹캠은 선택.`)
    },
    undefined,
    (err) => {
      console.error(err)
      setStatus('VRM 로드 실패 — 직접 .vrm 파일을 불러오세요.')
    },
  )
}

vrmFileEl.addEventListener('change', () => {
  const file = vrmFileEl.files?.[0]
  if (file) loadVRM(URL.createObjectURL(file))
})

// ---------------------------------------------------------------------------
// 리깅 헬퍼
// ---------------------------------------------------------------------------
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
type XYZ = { x: number; y: number; z: number }

function rigRotation(name: BoneName, rot: XYZ, dampener = 1, lerpAmount = 0.3) {
  const bone = currentVrm?.humanoid.getNormalizedBoneNode(name)
  if (!bone) return
  const flip = SETTINGS.mirror ? -1 : 1
  const euler = new THREE.Euler(rot.x * dampener, rot.y * dampener * flip, rot.z * dampener * flip, 'XYZ')
  bone.quaternion.slerp(new THREE.Quaternion().setFromEuler(euler), lerpAmount)
}

function rigPosition(name: BoneName, pos: XYZ, dampener = 1, lerpAmount = 0.3) {
  const bone = currentVrm?.humanoid.getNormalizedBoneNode(name)
  if (!bone) return
  bone.position.lerp(new THREE.Vector3(pos.x * dampener, pos.y * dampener, pos.z * dampener), lerpAmount)
}

function setExpr(name: string, value: number, smoothing = 0.4) {
  const em = currentVrm?.expressionManager
  if (!em || !em.getExpression(name)) return
  em.setValue(name, lerp(em.getValue(name) ?? 0, value, smoothing))
}

// --- 얼굴 ---
let prevYaw = 0
let prevPitch = 0
function rigFace(r: Kalidokit.TFace) {
  if (!currentVrm) return
  lastFaceTime = performance.now()
  rigRotation('neck', r.head, 0.7, 0.3)

  const stab = Kalidokit.Face.stabilizeBlink({ l: r.eye.l, r: r.eye.r }, r.head.y)
  setExpr('blink', 1 - stab.l, 0.5)

  // 말하는 중에는 입을 TTS 음량(applyMouth)이 구동하므로 웹캠 입추적은 양보한다.
  if (!speech.speaking) {
    setExpr('aa', r.mouth.shape.A)
    setExpr('ih', r.mouth.shape.I)
    setExpr('ou', r.mouth.shape.U)
    setExpr('ee', r.mouth.shape.E)
    setExpr('oh', r.mouth.shape.O)
  }

  // 눈동자 (lookAt yaw/pitch, 단위: 도)
  if (currentVrm.lookAt) {
    const dir = SETTINGS.mirror ? -1 : 1
    prevYaw = lerp(prevYaw, r.pupil.x * SETTINGS.pupilRange * dir, 0.4)
    prevPitch = lerp(prevPitch, -r.pupil.y * SETTINGS.pupilRange, 0.4)
    currentVrm.lookAt.yaw = prevYaw
    currentVrm.lookAt.pitch = prevPitch
  }
}

// --- 상체 ---
function rigPose(p: Kalidokit.TPose) {
  if (p.Hips.rotation) rigRotation('hips', p.Hips.rotation, 0.7, 0.3)
  if (SETTINGS.applyHipsPosition) {
    rigPosition(
      'hips',
      { x: p.Hips.position.x, y: p.Hips.position.y + 1, z: -p.Hips.position.z },
      1,
      0.07,
    )
  }
  rigRotation('chest', p.Spine, 0.25, 0.3)
  rigRotation('spine', p.Spine, 0.45, 0.3)

  // 팔: 출력단 축부호(q/w/e) + 좌우스왑(r) 보정
  const fix = (v: XYZ): XYZ => ({ x: v.x * armFix.x, y: v.y * armFix.y, z: v.z * armFix.z })
  const mir = (v: XYZ): XYZ => ({ x: v.x, y: -v.y, z: -v.z }) // 좌우 미러
  const RUA = armFix.swap ? mir(p.LeftUpperArm) : p.RightUpperArm
  const RLA = armFix.swap ? mir(p.LeftLowerArm) : p.RightLowerArm
  const LUA = armFix.swap ? mir(p.RightUpperArm) : p.LeftUpperArm
  const LLA = armFix.swap ? mir(p.RightLowerArm) : p.LeftLowerArm
  rigRotation('rightUpperArm', fix(RUA), 1, 0.3)
  rigRotation('rightLowerArm', fix(RLA), 1, 0.3)
  rigRotation('leftUpperArm', fix(LUA), 1, 0.3)
  rigRotation('leftLowerArm', fix(LLA), 1, 0.3)
}

// --- 손/손가락 ---
const FINGERS = ['Index', 'Middle', 'Ring', 'Little'] as const
const SEGS = ['Proximal', 'Intermediate', 'Distal'] as const
// 엄지: Kalidokit 세그먼트 -> VRM 세그먼트
const THUMB: ReadonlyArray<readonly [string, string]> = [
  ['Proximal', 'Metacarpal'],
  ['Intermediate', 'Proximal'],
  ['Distal', 'Distal'],
]

function rigHand(side: 'Left' | 'Right', hand: Record<string, XYZ>, poseWrist?: XYZ) {
  const lo = side.toLowerCase() // 'left' | 'right'
  const wrist = hand[`${side}Wrist`]
  if (wrist) {
    rigRotation(`${lo}Hand` as BoneName, { x: wrist.x, y: wrist.y, z: poseWrist?.z ?? wrist.z }, 1, 0.3)
  }
  for (const finger of FINGERS) {
    for (const seg of SEGS) {
      const v = hand[`${side}${finger}${seg}`]
      if (v) rigRotation(`${lo}${finger}${seg}` as BoneName, v, 1, 0.3)
    }
  }
  for (const [kdSeg, vrmSeg] of THUMB) {
    const v = hand[`${side}Thumb${kdSeg}`]
    if (v) rigRotation(`${lo}Thumb${vrmSeg}` as BoneName, v, 1, 0.3)
  }
}

// ---------------------------------------------------------------------------
// MediaPipe Holistic
// ---------------------------------------------------------------------------
let holistic: HolisticLandmarker | null = null

async function initHolistic() {
  setStatus('전신 추적 모델 로딩 중… (최초 1회, 잠시 대기)')
  const fileset = await FilesetResolver.forVisionTasks(
    'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm',
  )
  holistic = await HolisticLandmarker.createFromOptions(fileset, {
    baseOptions: {
      modelAssetPath:
        'https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/holistic_landmarker.task',
      delegate: 'GPU',
    },
    runningMode: 'VIDEO',
  })
}

async function startCamera() {
  camBtn.disabled = true
  try {
    if (!holistic) await initHolistic()
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
      audio: false,
    })
    videoEl.srcObject = stream
    await videoEl.play()
    setStatus('추적 중 — 머리·표정·상체·손을 움직여 보세요.')
  } catch (err) {
    console.error(err)
    setStatus('웹캠/모델 시작 실패: ' + (err as Error).message)
    camBtn.disabled = false
  }
}

camBtn.addEventListener('click', startCamera)

// ---------------------------------------------------------------------------
// 메인 루프
// ---------------------------------------------------------------------------
const clock = new THREE.Clock()
let lastVideoTime = -1
let lastFaceTime = 0

// 발화 중에는 TTS 음량으로 입('aa')을 구동한다. 웹캠이 꺼져 있어도(rigFace 미실행)
// 캐릭터가 말할 수 있도록 렌더 루프에서 매 프레임 직접 적용한다.
function applyMouth() {
  if (!currentVrm) return
  const faceActive = performance.now() - lastFaceTime < 200
  if (speech.speaking) {
    setExpr('aa', Math.min(1, speech.mouthOpen), 0.3) // 0.5→0.3: 더 빠른 반응
    setExpr('ih', 0, 0.5)
    setExpr('ou', 0, 0.5)
    setExpr('ee', 0, 0.5)
    setExpr('oh', 0, 0.5)
  } else if (!faceActive) {
    setExpr('aa', 0, 0.3) // 웹캠 없이 발화가 끝나면 입을 다문다.
  }
}

// 웹캠 추적이 없을 때 캐릭터가 스스로 살아있게 만드는 자동 모션.
// 숨쉬기·고개 살랑임·둘러보기·눈깜빡임을 기본으로, 말하는 중엔 머리 움직임을 키워
// '사람과 대화하는' 느낌을 준다. 모든 값은 작게(라디안) 잡아 과하지 않게.
let lastTrackTime = 0
const REST_ARM_Z = 1.18
let nextBlinkAt = 0
let blinkUntil = 0
// 아이들 미소
let nextSmileAt = 0
let smileUntil = 0
// 봇 감정 표정 유지 타이머
let emotionUntil = 0

function idleAnimate() {
  if (!currentVrm) return
  const t = performance.now() / 1000
  const now = performance.now()
  const talk = speech.speaking ? 1.8 : 1 // 말할 때 움직임 증폭

  // 호흡 — 가슴·척추 미세 상하
  const breath = Math.sin(t * 1.1) * 0.02
  rigRotation('spine', { x: breath, y: Math.sin(t * 0.33) * 0.02, z: 0 }, 1, 0.08)
  rigRotation('chest', { x: breath * 0.6, y: 0, z: 0 }, 1, 0.08)

  // 머리·목 — 천천히 살랑이고, 발화 중엔 끄덕임 추가
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

  // 허리 — 약한 무게중심 이동
  rigRotation('hips', { x: 0, y: Math.sin(t * 0.27) * 0.04, z: Math.sin(t * 0.6) * 0.015 }, 1, 0.05)

  // 팔 — T-포즈를 자연스럽게 내린 휴식 자세 + 미세 흔들림
  // (이 모델 기준: 왼팔 -z / 오른팔 +z 가 '아래'. 반대로 솟으면 이 두 부호를 다시 뒤집어라)
  const armSway = Math.sin(t * 0.8) * 0.04
  rigRotation('leftUpperArm', { x: 0.05, y: 0, z: -REST_ARM_Z - armSway }, 1, 0.06)
  rigRotation('rightUpperArm', { x: 0.05, y: 0, z: REST_ARM_Z + armSway }, 1, 0.06)
  rigRotation('leftLowerArm', { x: 0, y: -0.25, z: -0.1 }, 1, 0.06)
  rigRotation('rightLowerArm', { x: 0, y: 0.25, z: 0.1 }, 1, 0.06)

  // 눈동자 — 천천히 둘러보기
  if (currentVrm.lookAt) {
    currentVrm.lookAt.yaw = Math.sin(t * 0.3) * 9
    currentVrm.lookAt.pitch = Math.sin(t * 0.22) * 4
  }

  // 자동 눈깜빡임 — 2.5~6초 간격으로 120ms
  if (now > nextBlinkAt) {
    blinkUntil = now + 120
    nextBlinkAt = now + 2500 + Math.random() * 3500
  }
  setExpr('blink', now < blinkUntil ? 1 : 0, 0.5)

  // 아이들 미소 — 15~35초마다 2~4초간 자연스럽게 (applyEmotion과 공존)
  if (now > nextSmileAt) {
    smileUntil = now + 2000 + Math.random() * 2000
    nextSmileAt = now + 15000 + Math.random() * 20000
  }
  if (now > emotionUntil) {
    const smileVal = now < smileUntil ? 0.35 : 0
    setExpr('happy', smileVal, 0.05)
    setExpr('joy', smileVal, 0.05) // VRM 0.0 호환
  }
}

// VRM 0.0 / 1.0 양쪽 표정 이름 매핑
const EMOTION_MAP: Record<string, string[]> = {
  happy: ['happy', 'joy'],
  sad: ['sad', 'sorrow'],
  surprised: ['surprised', 'fun'],
}
const ALL_EMOTION_EXPRS = ['happy', 'joy', 'sad', 'sorrow', 'surprised', 'fun', 'relaxed', 'angry']

// 봇 응답 감정 표정 적용. 4초간 유지 후 neutral로 페이드.
function applyEmotion() {
  if (!currentVrm) return
  const now = performance.now()

  if (emotion.name) {
    // 새 감정 신호 수신 → 4초간 유지
    emotionUntil = now + 4000
    const targets = EMOTION_MAP[emotion.name] ?? [emotion.name]
    for (const e of ALL_EMOTION_EXPRS) {
      setExpr(e, targets.includes(e) ? emotion.intensity : 0, 0.08)
    }
    emotion.name = '' // 소비
  } else if (now < emotionUntil) {
    // 유지 중 → 아무것도 안 함 (이미 setExpr로 고정됨)
  } else if (now < emotionUntil + 1000) {
    // 유지 끝 → neutral로 페이드아웃
    for (const e of ALL_EMOTION_EXPRS) setExpr(e, 0, 0.04)
  }
}

function updateDebug(raw3d: Array<{ x: number; y: number; z: number }>, pose: Kalidokit.TPose) {
  const n = (v: number) => (v >= 0 ? ' ' : '') + v.toFixed(2)
  const lm = (i: number) => (raw3d[i] ? `${n(raw3d[i].x)},${n(raw3d[i].y)},${n(raw3d[i].z)}` : '—')
  const eu = (e: { x: number; y: number; z: number }) => `${n(e.x)},${n(e.y)},${n(e.z)}`
  const sgn = (v: number) => (v > 0 ? '+' : '-')
  dbgEl.textContent = [
    `arm 부호  q:x${sgn(armFix.x)}  w:y${sgn(armFix.y)}  e:z${sgn(armFix.z)}   r:swap=${armFix.swap}`,
    `raw world  shoulder ${lm(11)}`,
    `           elbow    ${lm(13)}`,
    `           wrist    ${lm(15)}`,
    `--- solved euler (x,y,z) ---`,
    `L UpperArm ${eu(pose.LeftUpperArm)}`,
    `R UpperArm ${eu(pose.RightUpperArm)}`,
  ].join('\n')
}

function track() {
  if (!holistic || videoEl.readyState < 2 || videoEl.currentTime === lastVideoTime) return
  lastVideoTime = videoEl.currentTime
  const res = holistic.detectForVideo(videoEl, performance.now())

  const face = res.faceLandmarks?.[0]
  if (face?.length) {
    const rf = Kalidokit.Face.solve(face, { runtime: 'mediapipe', video: videoEl })
    if (rf) rigFace(rf)
  }

  let pose: Kalidokit.TPose | undefined
  const pose2d = res.poseLandmarks?.[0]
  const raw3d = res.poseWorldLandmarks?.[0]
  if (pose2d?.length && raw3d?.length) {
    // 입력은 GitHub 원본 그대로 (좌표 변환 없음). 보정은 출력단(rigPose)에서 처리
    pose = Kalidokit.Pose.solve(raw3d, pose2d, {
      runtime: 'mediapipe',
      video: videoEl,
      enableLegs: false,
    })
    if (pose) rigPose(pose)
    if (SETTINGS.debug && pose) updateDebug(raw3d, pose)
  } else if (SETTINGS.debug) {
    dbgEl.textContent = `pose 미검출 (2d=${pose2d?.length ?? 0}, 3d=${raw3d?.length ?? 0})\n상반신이 카메라에 들어오게 해주세요`
  }

  const lh = res.leftHandLandmarks?.[0]
  if (lh?.length) {
    const solved = Kalidokit.Hand.solve(lh, 'Left') as Record<string, XYZ> | undefined
    if (solved) rigHand('Left', solved, pose?.LeftHand)
  }
  const rh = res.rightHandLandmarks?.[0]
  if (rh?.length) {
    const solved = Kalidokit.Hand.solve(rh, 'Right') as Record<string, XYZ> | undefined
    if (solved) rigHand('Right', solved, pose?.RightHand)
  }

  // 웹캠이 실제로 무언가를 추적한 순간을 기록 → 추적이 없을 때만 자동 아이들 모션을 돌린다.
  if (face?.length || pose2d?.length || lh?.length || rh?.length) {
    lastTrackTime = performance.now()
  }
}

function animate() {
  requestAnimationFrame(animate)
  track()
  // 웹캠 추적이 끊긴(또는 시작 안 한) 상태면 자동 아이들 모션으로 캐릭터를 살아있게.
  if (performance.now() - lastTrackTime > 400) idleAnimate()
  applyEmotion()
  applyMouth()
  if (currentVrm) currentVrm.update(clock.getDelta())
  renderer.render(scene, camera)
}

// ---------------------------------------------------------------------------
initChat()
loadVRM(DEFAULT_VRM_URL)
animate()
