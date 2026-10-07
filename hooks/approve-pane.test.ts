// `claude plugin test .` from the repository root: the approve pane against a fake `antstreet`
// answered beneath the plugin (no process, file, network or model call is made).
import { expect, mock, test } from 'claude-code/testing'

const VALUE = '0123456789abcdef'
const SHEET = `TERM SHEET\n  c01: reverse('ab') == 'ba'\n\nRun r1 is awaiting the investor's approval. Read it; to approve, run this yourself:\n  boss approve r1 --sheet ${VALUE}\n`
const BAND = { component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false } } as const

type Fake = { calls: string[][]; writes: { path: string; text: string }[] }

// A fake CLI: `status --json` says r1 waits until an approve with the right value lands.
function fakeCli(on: Parameters<Parameters<typeof test>[1] & Function>[1], opts: { run?: string; approveExit?: number } = {}): Fake {
  const fake: Fake = { calls: [], writes: [] }
  let approved = false
  on('session.start', async (_$, e) => ({ cwd: e.cwd }))
  on('process.run', async (_$, e) => {
    const args = e.argv.slice(2) // after `uvx antstreet`
    fake.calls.push([...e.argv])
    const ok = (stdout: string, exitCode = 0) => ({
      value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    })
    if (args[0] === 'status') return ok(JSON.stringify({ run: opts.run ?? 'r1', awaiting: !approved }))
    if (args[0] === 'approve' && args.length === 2) return ok(SHEET)
    if (args[0] === 'approve' && args[2] === '--sheet') {
      const exit = opts.approveExit ?? 0
      approved = exit === 0 && args[3] === VALUE
      return ok(approved ? 'Approved run r1. Build it with `boss resume r1`.' : 'Not approved: changed.', exit)
    }
    return ok('', 2)
  })
  on('fs.read', async () => ({ deny: 'ENOENT' }))
  on('fs.write', async (_$, e) => {
    fake.writes.push({ path: e.path, text: e.text })
    return { value: undefined }
  })
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('ui.close', async () => ({ value: undefined }))
  on('ui.render', async ($, e) => h($.ui.resolve(e).Box, null)) // the engine's own drawing
  return fake
}

const sheetCalls = (fake: Fake) => fake.calls.filter(argv => argv.includes('--sheet'))

async function band($: any) {
  await $.session.start({ cwd: '/project', surface: 'terminal', isInteractive: true })
  for (let i = 0; i < 50; i++) {
    const ui = await $.ui.mount({ plugin: 'antstreet', surface: 'terminal', ...BAND })
    if (await ui.find({ key: 'review' })) return ui
    await ui.unmount()
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  throw new Error('the band never showed Review')
}

test('a waiting run shows the sheet, and only the Approve press approves, timed', async ($, on) => {
  const clock = mock.clock(on)
  const fake = fakeCli(on)
  const ui = await band($)
  expect(sheetCalls(fake)).toEqual([]) // session start and drawing never approve
  await ui.press({ key: 'review' })
  for (const surface of ['terminal', 'desktop'] as const) {
    const pane = await $.ui.mount({ plugin: 'antstreet', surface, component: 'Pane', requestId: 'antstreet-approve', props: {} as any })
    expect((await pane.find({ type: 'Text', text: "reverse('ab') == 'ba'" }))?.text).toContain('TERM SHEET')
    expect(await pane.find({ type: 'Text', text: 'is awaiting the investor' })).toBeUndefined()
    expect((await pane.find({ key: 'approve' }))?.props.hotkey).toBeUndefined()
    await pane.unmount()
  }
  expect(sheetCalls(fake)).toEqual([])
  await clock.advance(42_000)
  const pane = await $.ui.mount({ plugin: 'antstreet', surface: 'terminal', component: 'Pane', requestId: 'antstreet-approve', props: {} as any })
  await pane.press({ key: 'approve' })
  expect(sheetCalls(fake)).toEqual([['uvx', 'antstreet', 'approve', 'r1', '--sheet', VALUE]])
  expect(await pane.find({ type: 'Text', text: 'Approved run r1' })).toBeDefined()
  expect(await pane.find({ key: 'approve' })).toBeUndefined() // nothing waits any more
  const [written] = fake.writes
  expect(written?.path.endsWith('/.boss/approve-timings.jsonl')).toBe(true)
  const line = JSON.parse(written?.text ?? '{}')
  expect(line).toEqual(expect.objectContaining({ run: 'r1', sheet: VALUE, ms: 42_000, exit_code: 0, surface: 'terminal' }))
})

test('a refused approval is shown in the pane and still timed', async ($, on) => {
  mock.clock(on)
  const fake = fakeCli(on, { approveExit: 1 })
  const ui = await band($)
  await ui.press({ key: 'review' })
  const pane = await $.ui.mount({ plugin: 'antstreet', surface: 'terminal', component: 'Pane', requestId: 'antstreet-approve', props: {} as any })
  await pane.press({ key: 'approve' })
  expect(await pane.find({ type: 'Text', text: 'Not approved' })).toBeDefined()
  expect(JSON.parse(fake.writes[0]?.text ?? '{}').exit_code).toBe(1)
})

test('a run id that could read as an option is never passed to approve', async ($, on) => {
  mock.clock(on)
  const fake = fakeCli(on, { run: '--sheet' })
  await $.session.start({ cwd: '/project', surface: 'terminal', isInteractive: true })
  await new Promise(resolve => setTimeout(resolve, 50))
  const ui = await $.ui.mount({ plugin: 'antstreet', surface: 'terminal', ...BAND })
  expect(await ui.find({ key: 'review' })).toBeUndefined()
  expect(fake.calls.filter(argv => argv[2] === 'approve')).toEqual([])
})
