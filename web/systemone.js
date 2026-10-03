import { app } from '../../scripts/app.js'
import { ComfyWidgets } from '../../scripts/widgets.js'

const JUDGMENT_NODES = new Set([
  'SystemOneChoice',
  'SystemOneNoul',
  'SystemOneScore',
  'SystemOneImageCheck',
  'SystemOnePickBestImage'
])
const PREVIEW = 'answer'

function showAnswer(node, text) {
  let widget = node.widgets?.find((w) => w.name === PREVIEW)
  if (!widget) {
    widget = ComfyWidgets.STRING(node, PREVIEW, ['STRING', { multiline: true }], app).widget
    widget.serialize = false
    if (widget.inputEl) {
      widget.inputEl.readOnly = true
      widget.inputEl.style.fontFamily = 'monospace'
    }
  }
  widget.value = text
  node.setDirtyCanvas(true, true)
}

app.registerExtension({
  name: 'SystemOne.AnswerPreview',
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!JUDGMENT_NODES.has(nodeData.name)) return
    const onExecuted = nodeType.prototype.onExecuted
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments)
      showAnswer(this, (message?.text ?? []).join('\n'))
    }
  }
})
