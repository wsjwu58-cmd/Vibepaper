import { Outlet } from 'react-router-dom'
import { PillNav } from '@/components/ui/PillNav'

export function HubLayout() {
  return (
    <div className="vp-hub-shell">
      <div className="pointer-events-none sticky top-0 z-40 px-3 pt-5 pb-1">
        <div className="pointer-events-auto">
          <PillNav />
        </div>
      </div>
      <main className="w-full px-5 pb-20 pt-10 md:px-8 lg:px-10">
        <Outlet />
      </main>
    </div>
  )
}
