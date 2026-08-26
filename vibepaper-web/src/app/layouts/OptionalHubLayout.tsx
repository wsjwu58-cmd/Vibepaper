import { Outlet, Link } from 'react-router-dom'
import { PillNav } from '@/components/ui/PillNav'
import { useAuth } from '@/lib/auth'
import { useEffect } from 'react'

/** Hub shell that works for guests (创意广场公开浏览) and logged-in users. */
export function OptionalHubLayout() {
  const ready = useAuth((s) => s.ready)
  const user = useAuth((s) => s.user)
  const load = useAuth((s) => s.load)

  useEffect(() => {
    if (!ready) void load()
  }, [ready, load])

  return (
    <div className="vp-hub-shell min-h-screen">
      <div className="pointer-events-none sticky top-0 z-40 px-3 pt-5 pb-1">
        <div className="pointer-events-auto">
          {user ? (
            <PillNav />
          ) : (
            <div className="mx-auto flex max-w-6xl items-center justify-between rounded-[22px] border border-black/6 bg-white/90 px-4 py-2.5 shadow-sm backdrop-blur">
              <Link to="/gallery" className="text-[15px] font-black text-[#111]">
                创意广场
              </Link>
              <div className="flex gap-2">
                <Link
                  to="/login"
                  className="rounded-full px-3 py-1.5 text-[13px] font-semibold text-[#555] hover:bg-black/5"
                >
                  登录
                </Link>
                <Link
                  to="/register"
                  className="rounded-full bg-[#111] px-3 py-1.5 text-[13px] font-semibold text-white"
                >
                  注册
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
      <main className="w-full px-5 pb-20 pt-10 md:px-8 lg:px-10">
        <Outlet />
      </main>
    </div>
  )
}
