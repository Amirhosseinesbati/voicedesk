import { useCallback, useEffect, useRef, useState } from 'react'

export type VoiceStatus = 'idle' | 'connecting' | 'listening' | 'processing' | 'speaking' | 'replay' | 'disconnected' | 'error'

interface ServerEvent {
  type: string
  status?: string
  turn_id?: string
  text?: string
  audio?: string
  detail?: string
  message?: string
  verification_code?: string | null
}

function encodePcm(samples: number[]): string {
  const bytes = new Uint8Array(samples.length * 2)
  const view = new DataView(bytes.buffer)
  samples.forEach((sample, index) => view.setInt16(index * 2, Math.max(-32768, Math.min(32767, Math.round(sample * 32767))), true))
  let binary = ''
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]!)
  return btoa(binary)
}

function decodePcm(base64: string): Float32Array {
  const binary = atob(base64)
  const view = new DataView(new ArrayBuffer(binary.length))
  for (let index = 0; index < binary.length; index += 1) view.setUint8(index, binary.charCodeAt(index))
  const samples = new Float32Array(binary.length / 2)
  for (let index = 0; index < samples.length; index += 1) samples[index] = view.getInt16(index * 2, true) / 32768
  return samples
}

function downsample(input: Float32Array, sourceRate: number): number[] {
  if (sourceRate <= 24000) return Array.from(input)
  const ratio = sourceRate / 24000
  const output: number[] = []
  for (let outputIndex = 0; Math.floor((outputIndex + 1) * ratio) < input.length; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio)
    const end = Math.min(input.length, Math.floor((outputIndex + 1) * ratio))
    let total = 0
    for (let inputIndex = start; inputIndex < end; inputIndex += 1) total += input[inputIndex]!
    output.push(total / Math.max(1, end - start))
  }
  return output
}

export function useVoice(onServerEvent: (event: ServerEvent) => void) {
  const [status, setStatus] = useState<VoiceStatus>('idle')
  const [muted, setMuted] = useState(false)
  const [level, setLevel] = useState(0)
  const [outputLevel, setOutputLevel] = useState(0)
  const [error, setError] = useState('')
  const socketRef = useRef<WebSocket | null>(null)
  const inputContextRef = useRef<AudioContext | null>(null)
  const outputContextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const inputNodeRef = useRef<AudioWorkletNode | null>(null)
  const sourcesRef = useRef(new Set<AudioBufferSourceNode>())
  const outputAnalyserRef = useRef<AnalyserNode | null>(null)
  const outputMeterRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const playbackTokenRef = useRef(0)
  const playbackTimeRef = useRef(0)
  const samplesRef = useRef<number[]>([])
  const activeAssistantTurnRef = useRef<string | null>(null)
  const currentUserTurnRef = useRef<string | null>(null)
  const ignoredTurnsRef = useRef(new Set<string>())
  const mutedRef = useRef(false)
  const callbackRef = useRef(onServerEvent)
  const modeRef = useRef<'connected' | 'replay'>('connected')
  const deliberateStopRef = useRef(false)
  const lastMeterUpdateRef = useRef(0)

  useEffect(() => { callbackRef.current = onServerEvent }, [onServerEvent])

  const stopOutputMeter = useCallback(() => {
    if (outputMeterRef.current) clearInterval(outputMeterRef.current)
    outputMeterRef.current = null
    outputAnalyserRef.current?.disconnect()
    outputAnalyserRef.current = null
    setOutputLevel(0)
  }, [])

  const stopPlayback = useCallback(() => {
    playbackTokenRef.current += 1
    for (const source of sourcesRef.current) {
      try { source.stop() } catch { /* An ended source cannot be stopped twice. */ }
    }
    sourcesRef.current.clear()
    playbackTimeRef.current = 0
    stopOutputMeter()
  }, [stopOutputMeter])

  const releaseMedia = useCallback(() => {
    inputNodeRef.current?.disconnect()
    inputNodeRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void inputContextRef.current?.close()
    inputContextRef.current = null
    setLevel(0)
  }, [])

  const stop = useCallback(() => {
    deliberateStopRef.current = true
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'stop' }))
    socketRef.current?.close(1000, 'User ended session')
    socketRef.current = null
    releaseMedia()
    stopPlayback()
    currentUserTurnRef.current = null
    activeAssistantTurnRef.current = null
    samplesRef.current = []
    void outputContextRef.current?.close()
    outputContextRef.current = null
    setStatus('idle')
    setError('')
  }, [releaseMedia, stopPlayback])

  const interrupt = useCallback(() => {
    if (activeAssistantTurnRef.current) ignoredTurnsRef.current.add(activeAssistantTurnRef.current)
    stopPlayback()
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'interrupt', turn_id: activeAssistantTurnRef.current }))
    activeAssistantTurnRef.current = null
    setStatus(modeRef.current === 'replay' ? 'replay' : 'listening')
  }, [stopPlayback])

  const playChunk = useCallback(async (audio: string, turnId?: string) => {
    if (turnId && ignoredTurnsRef.current.has(turnId)) return
    const playbackToken = playbackTokenRef.current
    const context = outputContextRef.current ?? new AudioContext({ sampleRate: 24000 })
    outputContextRef.current = context
    if (context.state === 'suspended') await context.resume()
    if (playbackToken !== playbackTokenRef.current || (turnId && ignoredTurnsRef.current.has(turnId))) return
    const samples = decodePcm(audio)
    const buffer = context.createBuffer(1, samples.length, 24000)
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0)
    const source = context.createBufferSource()
    let analyser = outputAnalyserRef.current
    if (!analyser) {
      analyser = context.createAnalyser()
      analyser.fftSize = 256
      analyser.connect(context.destination)
      outputAnalyserRef.current = analyser
    }
    source.buffer = buffer
    source.connect(analyser)
    const start = Math.max(context.currentTime + 0.02, playbackTimeRef.current)
    playbackTimeRef.current = start + buffer.duration
    source.start(start)
    sourcesRef.current.add(source)
    if (!outputMeterRef.current) {
      const samples = new Float32Array(analyser.fftSize)
      outputMeterRef.current = setInterval(() => {
        analyser.getFloatTimeDomainData(samples)
        let power = 0
        for (const sample of samples) power += sample * sample
        setOutputLevel(Math.min(1, Math.sqrt(power / samples.length) * 8))
      }, 90)
    }
    setStatus('speaking')
    source.onended = () => {
      if (!sourcesRef.current.has(source)) return
      sourcesRef.current.delete(source)
      if (sourcesRef.current.size === 0) {
        stopOutputMeter()
        setStatus(modeRef.current === 'replay' ? 'replay' : 'listening')
      }
    }
  }, [stopOutputMeter])

  const connect = useCallback(async (sessionId: string, mode: 'connected' | 'replay') => {
    stop()
    deliberateStopRef.current = false
    modeRef.current = mode
    setStatus('connecting')
    setError('')
    let media: MediaStream | null = null
    try {
      if (mode === 'connected') {
        if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error('This browser does not support live microphone streaming. Use the text alternative.')
        media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false })
        streamRef.current = media
      }
      const url = new URL(`/api/sessions/${encodeURIComponent(sessionId)}/stream`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = new WebSocket(url)
      socketRef.current = socket
      socket.onmessage = (message) => {
        let event: ServerEvent
        try { event = JSON.parse(message.data as string) as ServerEvent } catch { return }
        if (event.turn_id && ignoredTurnsRef.current.has(event.turn_id) && event.type === 'audio_chunk') return
        if (event.turn_id && (event.type === 'reply_text' || event.type === 'audio_chunk')) activeAssistantTurnRef.current = event.turn_id
        if (event.type === 'status') {
          if (event.status === 'connected') setStatus(mode === 'replay' ? 'replay' : 'listening')
          if (event.status === 'processing') setStatus('processing')
          if (event.status === 'listening') setStatus('listening')
        } else if (event.type === 'audio_chunk' && event.audio) {
          void playChunk(event.audio, event.turn_id).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : 'Audio playback failed.'))
        } else if (event.type === 'error') {
          setError(event.detail || event.message || 'The audio connection failed.')
          setStatus('error')
        } else if (event.type === 'done') {
          if (sourcesRef.current.size === 0) setStatus(mode === 'replay' ? 'replay' : 'listening')
        }
        callbackRef.current(event)
      }
      socket.onerror = () => { setError('Voice connection failed. Try again or use text.'); setStatus('error') }
      socket.onclose = () => {
        releaseMedia()
        stopPlayback()
        socketRef.current = null
        if (!deliberateStopRef.current) setStatus('disconnected')
      }
      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve()
        const initialError = socket.onerror
        socket.onerror = (event) => { initialError?.call(socket, event); reject(new Error('Could not establish a voice connection.')) }
      })
      if (mode === 'replay') { setStatus('replay'); return }
      socket.send(JSON.stringify({ type: 'start' }))

      const context = new AudioContext()
      inputContextRef.current = context
      await context.audioWorklet.addModule('/audio-capture-worklet.js')
      const source = context.createMediaStreamSource(media!)
      const processor = new AudioWorkletNode(context, 'voicedesk-capture')
      inputNodeRef.current = processor
      source.connect(processor)
      processor.connect(context.destination)
      processor.port.onmessage = (event: MessageEvent<Float32Array>) => {
        const input = event.data
        if (mutedRef.current || socket.readyState !== WebSocket.OPEN) return
        const samples = downsample(input, context.sampleRate)
        samplesRef.current.push(...samples)
        if (samplesRef.current.length >= 2400) {
          const chunk = samplesRef.current.splice(0, 2400)
          currentUserTurnRef.current ??= crypto.randomUUID()
          socket.send(JSON.stringify({ type: 'audio_chunk', turn_id: currentUserTurnRef.current, audio: encodePcm(chunk) }))
        }
        const now = Date.now()
        if (now - lastMeterUpdateRef.current > 120) {
          let power = 0
          for (const sample of input) power += sample * sample
          setLevel(Math.min(1, Math.sqrt(power / Math.max(1, input.length)) * 10))
          lastMeterUpdateRef.current = now
        }
      }
      setStatus('listening')
    } catch (cause) {
      media?.getTracks().forEach((track) => track.stop())
      socketRef.current?.close()
      socketRef.current = null
      releaseMedia()
      const message = cause instanceof Error ? cause.message : 'Could not start microphone.'
      setError(message)
      setStatus('error')
      throw cause
    }
  }, [playChunk, releaseMedia, stop, stopPlayback])

  const toggleMute = useCallback(() => {
    mutedRef.current = !mutedRef.current
    setMuted(mutedRef.current)
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'mute', muted: mutedRef.current }))
    if (mutedRef.current) setLevel(0)
  }, [])

  const finishTurn = useCallback(() => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    currentUserTurnRef.current ??= crypto.randomUUID()
    if (samplesRef.current.length) socketRef.current.send(JSON.stringify({ type: 'audio_chunk', turn_id: currentUserTurnRef.current, audio: encodePcm(samplesRef.current.splice(0)) }))
    socketRef.current.send(JSON.stringify({ type: 'end_turn', turn_id: currentUserTurnRef.current }))
    currentUserTurnRef.current = null
    setStatus('processing')
  }, [])

  const replayTurn = useCallback((text: string) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return false
    const turnId = crypto.randomUUID()
    socketRef.current.send(JSON.stringify({ type: 'replay_turn', turn_id: turnId, text }))
    setStatus('processing')
    return true
  }, [])

  useEffect(() => () => stop(), [stop])

  return { status, muted, level, outputLevel, error, connect, stop, interrupt, toggleMute, finishTurn, replayTurn }
}
