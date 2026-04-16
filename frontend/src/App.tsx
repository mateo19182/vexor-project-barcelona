import { Routes, Route, Navigate } from 'react-router-dom'

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
    </div>
  )
}

export default function App() {
  return (
    <div className="bg-polkadot min-h-screen text-text-primary flex flex-col">
      <Routes>
        <Route path="/" element={<Navigate to="/new" replace />} />
        <Route path="/new" element={<PlaceholderPage title="New Case" />} />
        <Route path="/run/:runId" element={<PlaceholderPage title="Run View" />} />
      </Routes>
    </div>
  )
}
