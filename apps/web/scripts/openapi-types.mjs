/* global process, URL, fetch */
import { readFile, writeFile } from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'

const source = process.env.VOICEDESK_OPENAPI_URL || 'http://127.0.0.1:8000/openapi.json'
const outputPath = new URL('../src/lib/openapi.generated.ts', import.meta.url)
const check = process.argv.includes('--check')

const response = await fetch(source)
if (!response.ok) throw new Error(`OpenAPI fetch failed: ${response.status} ${response.statusText}`)
const schema = await response.json()
if (schema?.info?.title !== 'VoiceDesk API') throw new Error(`Expected VoiceDesk API OpenAPI schema at ${source}.`)
const generated = astToString(await openapiTS(schema))

if (check) {
  const current = await readFile(outputPath, 'utf8')
  if (current !== generated) throw new Error('Generated API types are stale. Run pnpm api:generate against the running API.')
  process.stdout.write('Generated API types match OpenAPI.\n')
} else {
  await writeFile(outputPath, generated, 'utf8')
  process.stdout.write(`Generated API types from ${source}.\n`)
}
