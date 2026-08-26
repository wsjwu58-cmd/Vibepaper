import { NavLink, Outlet } from 'react-router-dom'
import {
  ArrowLeft,
  Boxes,
  Coins,
  FileSearch,
  Image,
  KeyRound,
  LayoutDashboard,
  Megaphone,
  Package,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { cn } from '@/lib/cn'

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard }
type NavGroup = { title: string; items: NavItem[] }

const groups: NavGroup[] = [
  {
    title: '概览',
    items: [{ to: '/admin/dashboard', label: '仪表盘', icon: LayoutDashboard }],
  },
  {
    title: '运营编排',
    items: [
      { to: '/admin/users', label: '用户管理', icon: Users },
      { to: '/admin/gallery-review', label: '内容审核', icon: Boxes },
      { to: '/admin/assets', label: '素材治理', icon: Image },
    ],
  },
  {
    title: '计费运营',
    items: [
      { to: '/admin/packages', label: '充值套餐', icon: Package },
      { to: '/admin/transactions', label: '交易记录', icon: Coins },
    ],
  },
  {
    title: '内容配置',
    items: [
      { to: '/admin/models', label: '模型管理', icon: FileSearch },
      { to: '/admin/announcements', label: '公告管理', icon: Megaphone },
      { to: '/admin/api-keys', label: 'API Keys', icon: KeyRound },
    ],
  },
  {
    title: '审计',
    items: [{ to: '/admin/audit', label: '审计日志', icon: ShieldCheck }],
  },
]

export function AdminLayout() {
  return (
    <div className="flex min-h-screen bg-[#f6f6f7]">
      <aside className="flex w-[240px] shrink-0 flex-col border-r border-black/6 bg-white">
        <div className="border-b border-black/6 px-5 py-5">
          <p className="text-[15px] font-black text-[#111]">运营后台</p>
          <p className="mt-0.5 text-[12px] text-[#999]">Admin Console</p>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map((g) => (
            <div key={g.title} className="mb-4">
              <p className="mb-1.5 px-2 text-[11px] font-bold uppercase tracking-wide text-[#aaa]">{g.title}</p>
              <div className="flex flex-col gap-0.5">
                {g.items.map((it) => (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    className={({ isActive }) =>
                      cn(
                        'flex h-9 items-center gap-2 rounded-xl px-2.5 text-[13px] font-semibold transition',
                        isActive
                          ? 'bg-[#111] text-white'
                          : 'text-[#555] hover:bg-black/[0.04] hover:text-[#111]',
                      )
                    }
                  >
                    <it.icon size={15} strokeWidth={2.2} />
                    {it.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-black/6 p-3">
          <NavLink
            to="/workspace"
            className="flex h-9 items-center gap-2 rounded-xl px-2.5 text-[13px] font-semibold text-[#666] hover:bg-black/[0.04] hover:text-[#111]"
          >
            <ArrowLeft size={15} />
            返回画布管理
          </NavLink>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto px-6 py-6 md:px-8">
        <Outlet />
      </main>
    </div>
  )
}
