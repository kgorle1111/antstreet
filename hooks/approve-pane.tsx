// The approve pane: a Claude Code mod that only draws and calls the `antstreet` CLI. Every
// decision (is a run waiting, what the sheet says, whether the value still matches) is the CLI's.
// The one call that approves runs from the Approve Button's onPress and nowhere else: the mods API
// has no method that presses a Button, so the model cannot reach it (tests/test_plugin.py holds
// this source to that).
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Pending, Result } from './approve-pane-state'

const PANE = 'antstreet-approve'
const TIMINGS = '.boss/approve-timings.jsonl'
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const SHEET = /--sheet ([0-9a-f]{16})\b/g

const pending = atom({ plugin: 'antstreet', key: 'pending' } as const, null)
const shownAt = atom({ plugin: 'antstreet', key: 'shownAt' } as const, null)
const result = atom({ plugin: 'antstreet', key: 'result' } as const, null)
const hidden = atom({ plugin: 'antstreet', key: 'hidden' } as const, null)
const busy = atom({ plugin: 'antstreet', key: 'busy' } as const, false)

async function antstreet($: EngineInterface, cli: readonly string[], args: readonly string[]) {
  return $.process.run([...cli, ...args], { timeoutMs: 60_000 })
}

// What is waiting, read fresh from the CLI: `status --json`, then the sheet `approve RUN` shows.
// Anything unexpected (no run, a refusal, output that does not parse) reads as nothing waiting.
async function refresh($: EngineInterface, cli: readonly string[]): Promise<Pending | null> {
  let found: Pending | null = null
  try {
    const status = await antstreet($, cli, ['status', '--json'])
    const state = status.exitCode === 0 ? JSON.parse(status.stdout) : null
    const run = state?.awaiting === true ? state.run : null
    if (typeof run === 'string' && RUN_ID.test(run)) {
      const shown = await antstreet($, cli, ['approve', run])
      const values = new Set([...shown.stdout.matchAll(SHEET)].map(m => m[1]))
      const [sheet] = values
      if (shown.exitCode === 0 && values.size === 1 && sheet !== undefined) {
        const cut = shown.stdout.indexOf(`\nRun ${run} is awaiting`)
        const text = (cut < 0 ? shown.stdout : shown.stdout.slice(0, cut)).trimEnd()
        found = { run, sheet, text }
      }
    }
  } catch {
    found = null
  }
  await update($, pending, () => found)
  return found
}

async function review($: EngineInterface, cli: readonly string[]) {
  await update($, result, () => null)
  await refresh($, cli)
  await $.ui.open({ id: PANE, title: 'AntStreet: approve', focus: true, closeOnEscape: true })
  const now = await $.clock.now()
  await update($, shownAt, () => now)
}

// kn: read-then-write append, not atomic; two sessions approving in the same instant could drop a
// line. Fine for a friction metric; move the write into the CLI if it ever feeds a decision.
async function recordTiming($: EngineInterface, line: object) {
  const before = await $.fs.read(TIMINGS).catch(() => '')
  const text = typeof before === 'string' ? before : ''
  await $.fs.write(TIMINGS, `${text}${JSON.stringify(line)}\n`)
}

// The only place `approve --sheet` is run: from the Approve Button's onPress.
async function approve($: EngineInterface, cli: readonly string[], surface: string) {
  if (await read($, busy)) return
  const shown = await read($, pending)
  const openedAt = await read($, shownAt)
  if (shown === null) return
  await update($, busy, () => true)
  try {
    const pressedAt = await $.clock.now()
    const done = await antstreet($, cli, ['approve', shown.run, '--sheet', shown.sheet])
    const said = `${done.stdout}${done.stderr}`.trim()
    await update($, result, (): Result => ({ exitCode: done.exitCode, text: said }))
    const line = {
      run: shown.run,
      sheet: shown.sheet,
      shown_at_ms: openedAt,
      pressed_at_ms: pressedAt,
      ms: openedAt === null ? null : pressedAt - openedAt,
      exit_code: done.exitCode,
      surface,
    }
    await recordTiming($, line).catch(() => $.ui.toast(`AntStreet: could not write ${TIMINGS}`))
    await refresh($, cli)
  } catch (error) {
    const text = `Not approved: ${String(error)}`
    await update($, result, (): Result => ({ exitCode: -1, text }))
  } finally {
    await update($, busy, () => false)
  }
}

export const register: Register = (on, options) => {
  const cli = String(options.command ?? 'uvx antstreet')
    .split(/\s+/)
    .filter(Boolean)

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    void refresh($, cli)
    return started
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    void refresh($, cli) // the agent may have just run `antstreet fund` with no terminal (exit 4)
    return done
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const waiting = await read($, pending)
    if (e.props.hasSurvey || waiting === null || (await read($, hidden)) === waiting.run) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text>AntStreet run {waiting.run} is awaiting your approval. </Text>
        <Button key="review" label="Review" onPress={() => review($, cli)} />
        <Text> </Text>
        <Button key="hide" label="Hide" onPress={() => update($, hidden, () => waiting.run)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const shown = await read($, pending)
    const done = await read($, result)
    const isBusy = await read($, busy)
    return (
      <Box flexDirection="column">
        {done !== null && (
          <Text key="result" color={done.exitCode === 0 ? 'green' : 'red'} wrap="wrap">
            {done.text}
          </Text>
        )}
        {shown === null && done === null && (
          <Text dimColor>No AntStreet run is awaiting approval.</Text>
        )}
        {shown !== null && (
          <Box flexDirection="column">
            <Text key="sheet" wrap="wrap">
              {shown.text}
            </Text>
            <Text dimColor wrap="wrap">
              Approve records your signed approval of exactly the text above (value {shown.sheet})
              by running `antstreet approve {shown.run} --sheet {shown.sheet}`. It spends nothing;
              build it with `antstreet resume {shown.run}`. Close leaves the run waiting.
            </Text>
          </Box>
        )}
        <Box>
          <Button
            key="close"
            label="Close"
            role="dismiss"
            autoFocus
            onPress={() => $.ui.close({ id: PANE })}
          />
          <Text> </Text>
          {shown !== null && !isBusy && (
            <Button
              key="approve"
              label="Approve"
              variant="primary"
              onPress={pe => approve($, cli, pe.surface)}
            />
          )}
          {isBusy && <Text dimColor>Approving...</Text>}
        </Box>
      </Box>
    )
  })
}
