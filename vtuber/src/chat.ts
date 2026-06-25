// 챗봇 API 연동 + TTS 재생 + 음량 기반 립싱크.
// main.ts 는 `speech` 객체만 읽어 말하는 동안 입을 벌린다(렌더 루프에서 참조).

const API_BASE = (import.meta.env.VITE_CHAT_API as string | undefined) ?? 'http://localhost:8000'

export const speech = { speaking: false, mouthOpen: 0 }

// main.ts 렌더 루프에서 읽어 표정을 구동. name='' 이면 비활성.
export const emotion = { name: '', intensity: 0 }

function detectEmotion(text: string): { name: string; intensity: number } {
  if (/축하|잘하셨|훌륭|완벽|좋아요|합격|성공|추천드|화이팅|최고/.test(text))
    return { name: 'happy', intensity: 0.75 }
  if (/어렵|힘드|죄송|아쉽|안타깝|실망|불합격/.test(text))
    return { name: 'sad', intensity: 0.55 }
  if (/놀랍|대단|와[!,~]|오[!,~]|정말요|진짜요/.test(text))
    return { name: 'surprised', intensity: 0.65 }
  return { name: '', intensity: 0 }
}

const sessionId =
  (globalThis.crypto?.randomUUID?.() as string | undefined) ?? `web-${Date.now()}-${Math.random()}`

// 입장 전 모달에서 한 번 입력받아 매 /api/chat 호출에 함께 보내는 프로필.
// target_job이 비어 있으면 Tool들이 매번 "어떤 직무로 준비하세요?"를 반복해서 물어보게 된다.
const profile = {
  education: '',
  target_job: '',
  skills: [] as string[],
  experiences: [] as string[],
  certs: [] as string[],
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

// null이면 자유 대화(키워드 추론 + 일반 GPT 대화). 칩을 누르면 해당 Tool로 고정되어
// 매 메시지가 키워드 매칭 없이 바로 그 Tool로 간다 — 메시지에 키워드가 없어 일반 대화로
// 빠지며 맥락(예: 직무)이 끊기던 문제를 버튼 고정으로 막는다.
let selectedTool: string | null = null
let interviewMode: 'practice' | 'real' | null = null

function showInterviewModeSelect(): void {
  document.getElementById('interview-mode-card')?.remove()
  const log = $('chat-log')
  const card = document.createElement('div')
  card.id = 'interview-mode-card'
  card.className = 'msg bot'
  card.innerHTML = `
    <p class="mode-card-title">면접 모드를 선택해 주세요</p>
    <div class="mode-card-btns">
      <button class="mode-card-btn" data-mode="practice">
        <span class="mode-card-icon">🎓</span>
        <strong>연습 모드</strong>
        <small>질문 의도·가이드 포함</small>
      </button>
      <button class="mode-card-btn" data-mode="real">
        <span class="mode-card-icon">⚡</span>
        <strong>실전 모드</strong>
        <small>가이드 없이 실제처럼</small>
      </button>
    </div>
  `
  card.querySelectorAll<HTMLButtonElement>('.mode-card-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      interviewMode = btn.dataset.mode as 'practice' | 'real'
      card.remove()
      const input = $('chat-input') as HTMLInputElement
      input.value = '면접 질문 생성해줘'
      ;($('chat-send') as HTMLButtonElement).click()
    })
  })
  log.appendChild(card)
  log.scrollTop = log.scrollHeight
}

function initToolBar(): void {
  const chips = Array.from(document.querySelectorAll<HTMLButtonElement>('.tool-chip'))
  for (const chip of chips) {
    chip.addEventListener('click', () => {
      const newTool = chip.dataset.tool || null
      if (newTool !== selectedTool) interviewMode = null
      selectedTool = newTool
      for (const other of chips) other.classList.toggle('active', other === chip)
      if (selectedTool === 'interview' && interviewMode === null) {
        showInterviewModeSelect()
      }
    })
  }
}

function initProfileForm(): void {
  const overlay = $('profile-modal')
  const form = $('profile-form') as HTMLFormElement

  form.addEventListener('submit', (e) => {
    e.preventDefault()
    profile.target_job = ($('p-target-job') as HTMLInputElement).value.trim()
    profile.education = ($('p-education') as HTMLInputElement).value.trim()
    profile.skills = splitCsv(($('p-skills') as HTMLInputElement).value)
    profile.experiences = splitCsv(($('p-experiences') as HTMLInputElement).value)
    profile.certs = splitCsv(($('p-certs') as HTMLInputElement).value)
    overlay.classList.add('hide')
  })
}

let audioCtx: AudioContext | null = null
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T

// 응답 텍스트에서 첫 번째 HTTP URL을 추출.
function extractUrl(text: string): string | null {
  const m = text.match(/https?:\/\/[^\s)>]+/)
  return m ? m[0].replace(/[.,;:!?]$/, '') : null
}

function cleanForDisplay(md: string): string {
  return md
    .replace(/#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^>\s*/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function cleanForSpeech(md: string): string {
  return md
    .split('\n')
    .filter((line) => !/^\s*\|/.test(line) && !/^\s*[-|: ]+$/.test(line))
    .join(' ')
    .replace(/[#>*_`~]/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

async function speak(text: string): Promise<void> {
  const clean = cleanForSpeech(text).slice(0, 600)
  if (!clean) return

  let buf: ArrayBuffer
  try {
    const res = await fetch(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: clean }),
    })
    if (!res.ok) return
    buf = await res.arrayBuffer()
  } catch {
    return
  }

  if (!audioCtx) audioCtx = new AudioContext()
  await audioCtx.resume()
  const audioBuffer = await audioCtx.decodeAudioData(buf)

  const source = audioCtx.createBufferSource()
  source.buffer = audioBuffer
  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 512
  source.connect(analyser)
  analyser.connect(audioCtx.destination)

  const data = new Uint8Array(analyser.fftSize)
  speech.speaking = true

  const tick = () => {
    if (!speech.speaking) return
    analyser.getByteTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / data.length)
    // 8배 증폭 (기존 4배). TTS 음성 RMS 0.05~0.15 → mouthOpen 0.4~1.0
    speech.mouthOpen = Math.min(1, rms * 8)
    requestAnimationFrame(tick)
  }

  await new Promise<void>((resolve) => {
    source.onended = () => {
      speech.speaking = false
      speech.mouthOpen = 0
      resolve()
    }
    source.start()
    tick()
  })
}

function showLinkInStage(url: string) {
  const frame = document.getElementById('link-frame') as HTMLIFrameElement | null
  const close = $('link-close')
  if (!frame) return
  frame.src = url
  frame.classList.add('show')
  close?.classList.add('show')
}

function hideLinkInStage() {
  const frame = document.getElementById('link-frame') as HTMLIFrameElement | null
  const close = $('link-close')
  if (frame) {
    frame.classList.remove('show')
    frame.src = 'about:blank'
  }
  close?.classList.remove('show')
}

// 대화 히스토리 (최근 10턴 유지 — GPT 컨텍스트용)
const history: Array<{ role: string; content: string }> = []
const MAX_HISTORY = 10

export function initChat(): void {
  initProfileForm()
  initToolBar()

  const input = $('chat-input') as HTMLInputElement
  const sendBtn = $('chat-send') as HTMLButtonElement
  const log = $('chat-log')

  $('link-close')?.addEventListener('click', hideLinkInStage)

  const addMsg = (role: 'user' | 'bot', text: string): void => {
    const div = document.createElement('div')
    div.className = `msg ${role}`
    if (role === 'bot' && text.trimStart().startsWith('<')) {
      div.innerHTML = text
    } else {
      div.textContent = text
    }
    log.appendChild(div)
    log.scrollTop = log.scrollHeight
  }

  addMsg('bot', '안녕하세요! 무엇을 도와드릴까요? 직무·자소서·면접·자격증, 편하게 물어보세요.')

  const send = async () => {
    const message = input.value.trim()
    if (!message) return
    input.value = ''
    sendBtn.disabled = true
    addMsg('user', message)

    history.push({ role: 'user', content: message })
    if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY)

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: (selectedTool === 'interview' && interviewMode)
            ? `[${interviewMode === 'practice' ? '연습모드' : '실전모드'}] ${message}`
            : message,
          tool: selectedTool,
          profile: { session_id: sessionId, ...profile },
          history: history.slice(0, -1),
        }),
      })
      const data = (await res.json()) as { text: string; tts_text: string; tool: string; label: string }
      const isHtml = data.text.trimStart().startsWith('<')
      addMsg('bot', isHtml ? data.text : cleanForDisplay(data.text))

      history.push({ role: 'assistant', content: data.text })
      if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY)

      // 응답에 URL이 있으면 아바타 배경에 표시
      const url = extractUrl(data.text)
      if (url) showLinkInStage(url)

      const em = detectEmotion(data.text)
      emotion.name = em.name
      emotion.intensity = em.intensity

      await speak(data.tts_text || data.text)
    } catch {
      addMsg('bot', '챗봇 서버에 연결하지 못했어요 (uv run uvicorn app.api:app --port 8000).')
    } finally {
      sendBtn.disabled = false
    }
  }

  sendBtn.addEventListener('click', () => void send())
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') void send()
  })
}
