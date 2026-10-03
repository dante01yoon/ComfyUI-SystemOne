import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const [apiPath, promptNode, ...steps] = process.argv.slice(2)
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

const focusPromptBox = () =>
  page.evaluate((nodeId) => {
    const current = window.app.graph.getNodeById(Number(nodeId)).widgets.find((w) => w.name === 'value').value
    const el = [...document.querySelectorAll('textarea')].find((t) => t.value === current && t.isConnected)
    if (!el) return false
    el.focus()
    el.select()
    return document.activeElement === el
  }, promptNode)
const runButton = page.getByTestId('queue-button')

const setWidget = (spec) =>
  page.evaluate((spec) => {
    const [, nodeId, name, value] = spec.match(/^@(\d+)\.(\w+)=(.*)$/)
    const widget = window.app.graph.getNodeById(Number(nodeId)).widgets.find((w) => w.name === name)
    widget.value = value
    widget.callback?.(value)
    window.app.graph.setDirtyCanvas(true, true)
  }, spec)
const currentPrompt = () =>
  page.evaluate((nodeId) => window.app.graph.getNodeById(Number(nodeId)).widgets.find((w) => w.name === 'value').value, promptNode)

let index = 0
for (const step of steps) {
  if (step.startsWith('@')) {
    await setWidget(step)
    await page.waitForTimeout(1500)
    continue
  }
  if (step !== (await currentPrompt())) {
    if (!(await focusPromptBox())) throw new Error('prompt box did not take focus')
    await page.keyboard.press('Backspace')
    await page.keyboard.type(step, { delay: 35 })
    await page.mouse.click(1000, 1060)
    await page.waitForTimeout(500)
  }
  const done = page.evaluate(
    () => new Promise((resolve, reject) => {
      const api = window.app.api
      const finish = (handler) => (e) => {
        api.removeEventListener('execution_success', onSuccess)
        api.removeEventListener('execution_error', onError)
        handler(e)
      }
      const onSuccess = finish(() => resolve())
      const onError = finish((e) => reject(new Error(JSON.stringify(e.detail).slice(0, 300))))
      api.addEventListener('execution_success', onSuccess)
      api.addEventListener('execution_error', onError)
      setTimeout(() => reject(new Error('run did not finish in 120s')), 120_000)
    })
  )
  await runButton.click()
  await done
  await page.waitForTimeout(3500)
  await page.screenshot({ path: path.join(outDir, `${name}-${index++}.png`) })
}

const video = page.video()
await context.close()
fs.renameSync(await video.path(), path.join(outDir, `${name}.webm`))
await browser.close()
