import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const [apiPath, promptNode, ...prompts] = process.argv.slice(2)
const base = process.env.COMFY_URL ?? 'http://127.0.0.1:8199'
const outDir = process.env.OUT_DIR ?? 'recordings'
const size = { width: 1920, height: 1080 }
const name = path.basename(apiPath, '.api.json')

const settings = {
  'Comfy.TutorialCompleted': true,
  'Comfy.Minimap.Visible': false,
  'Comfy.Graph.CanvasInfo': false,
  'Comfy.Queue.QPOV2': true
}
for (const [id, value] of Object.entries(settings)) {
  await fetch(`${base}/api/settings/${id}`, { method: 'POST', body: JSON.stringify(value) })
}

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: size, recordVideo: { dir: outDir, size } })
const page = await context.newPage()
await page.goto(base)
await page.waitForFunction(() => window.app?.graph && window.app.vueAppReady !== false)
await page.waitForTimeout(1500)

const api = JSON.parse(fs.readFileSync(apiPath, 'utf8'))
await page.evaluate(async ([workflow, title]) => {
  await window.app.loadApiJson(workflow, title)
}, [api, name])
await page.evaluate((workflow) => {
  const graph = window.app.graph
  for (const [id, node] of Object.entries(workflow)) {
    const layout = node._meta?.layout
    const target = graph.getNodeById(Number(id))
    if (!layout || !target) continue
    target.pos = layout.pos
    if (layout.size) target.size = layout.size
    if (layout.collapsed && !target.flags?.collapsed) target.collapse()
    if (node._meta.title) target.title = node._meta.title
  }
  graph.setDirtyCanvas(true, true)
}, api)
await page.keyboard.press('Escape')
await page.mouse.click(1000, 1060)
await page.keyboard.press('.')
await page.waitForTimeout(800)

const uiWorkflow = await page.evaluate(() => window.app.graph.serialize())
fs.writeFileSync(path.join(path.dirname(apiPath), `${name}.json`), JSON.stringify(uiWorkflow, null, 2))

for (const text of prompts) {
  await page.evaluate(([nodeId, value]) => {
    const node = window.app.graph.getNodeById(Number(nodeId))
    node.widgets.find((w) => w.name === 'value').value = value
    window.app.graph.setDirtyCanvas(true, true)
  }, [promptNode, text])
  await page.waitForTimeout(1200)
  const done = page.evaluate(
    () => new Promise((resolve) => {
      const onStatus = (e) => {
        if (e.detail?.exec_info?.queue_remaining === 0) {
          window.app.api.removeEventListener('status', onStatus)
          resolve()
        }
      }
      window.app.api.addEventListener('status', onStatus)
    })
  )
  await page.evaluate(() => window.app.queuePrompt(0))
  await done
  await page.waitForTimeout(3000)
  await page.screenshot({ path: path.join(outDir, `${name}-${prompts.indexOf(text)}.png`) })
}

await context.close()
await browser.close()
