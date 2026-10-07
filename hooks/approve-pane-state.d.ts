export type Pending = { run: string; sheet: string; text: string }
export type Result = { exitCode: number; text: string }

declare module 'claude-code' {
  interface PluginState {
    antstreet: {
      pending: Pending | null
      shownAt: number | null
      result: Result | null
      hidden: string | null
      busy: boolean
    }
  }
}
