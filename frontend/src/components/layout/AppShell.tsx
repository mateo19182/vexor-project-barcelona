import { TopNav } from './TopNav'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="bg-polkadot min-h-screen text-text-primary flex flex-col">
      <TopNav />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
