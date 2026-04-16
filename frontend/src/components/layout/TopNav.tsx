import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'

const navLinks = [
  { to: '/new', label: 'New Case' },
]

export function TopNav() {
  const location = useLocation()

  return (
    <header className="sticky top-0 z-50 h-14 bg-bg-surface border-b border-border-subtle flex items-center px-6">
      {/* Logotype */}
      <div className="border-l-2 border-text-primary pl-3">
        <span className="text-lg font-semibold text-text-primary tracking-tight">
          NORDES
        </span>
      </div>

      {/* Nav links */}
      <nav className="ml-auto flex items-center gap-6">
        {navLinks.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className={cn(
              'text-sm transition-colors duration-150',
              location.pathname === link.to
                ? 'text-text-primary'
                : 'text-text-secondary hover:text-text-primary'
            )}
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </header>
  )
}
