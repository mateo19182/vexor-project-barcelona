import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { HomePage } from '@/pages/HomePage'
import { RunPage } from '@/pages/RunPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/new" replace />} />
        <Route path="/new" element={<HomePage />} />
        <Route path="/run/:runId" element={<RunPage />} />
      </Routes>
    </AppShell>
  )
}
