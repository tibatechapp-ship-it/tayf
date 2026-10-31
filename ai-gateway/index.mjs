/**
 * Tayf Studio - AI gateway sidecar (real generation).
 *
 * Wraps z-ai-web-dev-sdk behind a tiny local HTTP API (the REAL provider path):
 *   GET  /health                 -> {status:"ok",service:"tayf-ai-gateway",...}
 *   POST /v1/chat  {messages}    -> {content}        (real LLM completion)
 *   POST /v1/image {prompt,size} -> {image_base64}   (real image model)
 *
 * Design rules:
 * - Binds 127.0.0.1 ONLY by default (override AI_GATEWAY_HOST for isolated docker networks).
 * - Optional shared token: set AI_GATEWAY_TOKEN and the Python backend will
 *   send it in the X-Gateway-Token header.
 * - Plain Node ESM, zero dependencies except the SDK itself (Termux-friendly).
 */

import http from 'node:http'
import crypto from 'node:crypto'
import ZAI from 'z-ai-web-dev-sdk'

const PORT = Number(process.env.AI_GATEWAY_PORT || 3030)
const HOST = process.env.AI_GATEWAY_HOST || '127.0.0.1'
const TOKEN = process.env.AI_GATEWAY_TOKEN || ''

const SUPPORTED_SIZES = new Set([
  '1024x1024', '768x1344', '864x1152', '1344x768', '1152x864', '1440x720', '720x1440',
])

let zaiInstance = null
async function getZAI() {
  if (!zaiInstance) zaiInstance = await ZAI.create()
  return zaiInstance
}

function send(res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) })
  res.end(body)
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > 8 * 1024 * 1024) { reject(new Error('body too large')); req.destroy(); return }
      chunks.push(chunk)
    })
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')) }
      catch (error) { reject(new Error('invalid JSON body')) }
    })
    req.on('error', reject)
  })
}

async function withRetry(label, attempts, fn) {
  let lastError
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error
      console.error(`[gateway] ${label} attempt ${attempt} failed: ${error.message}`)
      if (attempt < attempts) await new Promise((r) => setTimeout(r, 800 * attempt))
    }
  }
  throw lastError
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`)

  if (TOKEN && req.headers['x-gateway-token'] !== TOKEN) {
    return send(res, 401, { error: 'invalid gateway token' })
  }

  try {
    if (req.method === 'GET' && url.pathname === '/health') {
      return send(res, 200, {
        status: 'ok',
        service: 'tayf-ai-gateway',
        timestamp: new Date().toISOString(),
      })
    }

    if (req.method === 'POST' && url.pathname === '/v1/chat') {
      const body = await readBody(req)
      const messages = Array.isArray(body.messages) ? body.messages : null
      if (!messages || messages.length === 0) return send(res, 400, { error: 'messages[] required' })
      const content = await withRetry('chat', 2, async () => {
        const zai = await getZAI()
        const completion = await zai.chat.completions.create({
          messages,
          thinking: { type: 'disabled' },
        })
        const text = completion?.choices?.[0]?.message?.content
        if (!text || !String(text).trim()) throw new Error('empty completion')
        return String(text)
      })
      return send(res, 200, { content })
    }

    if (req.method === 'POST' && url.pathname === '/v1/image') {
      const body = await readBody(req)
      const prompt = String(body.prompt || '').trim()
      const size = String(body.size || '1024x1024')
      if (!prompt) return send(res, 400, { error: 'prompt required' })
      if (!SUPPORTED_SIZES.has(size)) {
        return send(res, 400, { error: `unsupported size ${size}; allowed: ${[...SUPPORTED_SIZES].join(',')}` })
      }
      const imageBase64 = await withRetry('image', 2, async () => {
        const zai = await getZAI()
        const response = await zai.images.generations.create({ prompt, size })
        const b64 = response?.data?.[0]?.base64
        if (!b64) throw new Error('no image data in response')
        return b64
      })
      // sanity: decode to confirm the payload is a real image
      const bytes = Buffer.from(imageBase64, 'base64')
      if (bytes.length < 1000) throw new Error('image payload too small')
      console.log(`[gateway] image OK ${size} ${bytes.length}B sha256=${crypto.createHash('sha256').update(bytes).digest('hex').slice(0, 12)}`)
      return send(res, 200, { image_base64: imageBase64 })
    }

    return send(res, 404, { error: `no route: ${req.method} ${url.pathname}` })
  } catch (error) {
    console.error(`[gateway] error: ${error.message}`)
    return send(res, 500, { error: error.message || 'internal gateway error' })
  }
})

server.listen(PORT, HOST, () => {
  console.log(`[gateway] tayf-ai-gateway listening on http://${HOST}:${PORT} (token: ${TOKEN ? 'enabled' : 'disabled'})`)
})
