import logoSvg from "@/assets/logo.svg";

export function TopNav() {
  return (
    <header className="sticky top-0 z-50 h-14 bg-bg-surface/60 backdrop-blur-xl border-b border-border-subtle flex items-center px-6">
      <img src={logoSvg} alt="Find" className="h-5" />
    </header>
  )
}
