import { Navigate, Route, Routes } from 'react-router-dom'
import { HubLayout } from '@/app/layouts/HubLayout'
import { OptionalHubLayout } from '@/app/layouts/OptionalHubLayout'
import { useAuth } from '@/lib/auth'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { WorkspacePage } from '@/features/workspace/WorkspacePage'
import { HistoryPage } from '@/features/history/HistoryPage'
import { GalleryPage } from '@/features/gallery/GalleryPage'
import { GalleryDetailPage } from '@/features/gallery/GalleryDetailPage'
import { GalleryProcessPage } from '@/features/gallery/GalleryProcessPage'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { EnterprisePage } from '@/features/enterprise/EnterprisePage'
import { SubscriptionsPage } from '@/features/subscriptions/SubscriptionsPage'
import { RewardsPage } from '@/features/rewards/RewardsPage'
import { InvitesPage } from '@/features/invites/InvitesPage'
import { AnnouncementsPage } from '@/features/announcements/AnnouncementsPage'
import { AdminLayout } from '@/features/admin/AdminLayout'
import { AdminDashboardPage } from '@/features/admin/pages/AdminDashboardPage'
import { AdminUsersPage } from '@/features/admin/pages/AdminUsersPage'
import { AdminGalleryReviewPage } from '@/features/admin/pages/AdminGalleryReviewPage'
import { AdminModelsPage } from '@/features/admin/pages/AdminModelsPage'
import { AdminPackagesPage } from '@/features/admin/pages/AdminPackagesPage'
import { AdminTransactionsPage } from '@/features/admin/pages/AdminTransactionsPage'
import { AdminAnnouncementsPage } from '@/features/admin/pages/AdminAnnouncementsPage'
import { AdminApiKeysPage } from '@/features/admin/pages/AdminApiKeysPage'
import { AdminAuditPage } from '@/features/admin/pages/AdminAuditPage'
import { AdminAssetsPage } from '@/features/admin/pages/AdminAssetsPage'
import { CanvasPage } from '@/features/canvas/CanvasPage'
import { Spinner } from '@/components/ui/Spinner'

function Protected({ children }: { children: React.ReactNode }) {
  const ready = useAuth((s) => s.ready)
  const user = useAuth((s) => s.user)
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  const ready = useAuth((s) => s.ready)
  const user = useAuth((s) => s.user)
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (user && (user.role === 'ops_admin' || user.role === 'super_admin')) return <>{children}</>
  return <Navigate to="/workspace" replace />
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<OptionalHubLayout />}>
        <Route path="/gallery" element={<GalleryPage />} />
      </Route>

      <Route path="/gallery/:id" element={<GalleryDetailPage />} />
      <Route path="/gallery/:id/process" element={<GalleryProcessPage />} />

      <Route
        element={
          <Protected>
            <HubLayout />
          </Protected>
        }
      >
        <Route path="/" element={<Navigate to="/workspace" replace />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/subscriptions" element={<SubscriptionsPage />} />
        <Route path="/rewards" element={<RewardsPage />} />
        <Route path="/invites" element={<InvitesPage />} />
        <Route path="/announcements" element={<AnnouncementsPage />} />
        <Route path="/enterprise" element={<EnterprisePage />} />
      </Route>

      <Route
        path="/admin"
        element={
          <Protected>
            <AdminGuard>
              <AdminLayout />
            </AdminGuard>
          </Protected>
        }
      >
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="gallery-review" element={<AdminGalleryReviewPage />} />
        <Route path="assets" element={<AdminAssetsPage />} />
        <Route path="models" element={<AdminModelsPage />} />
        <Route path="packages" element={<AdminPackagesPage />} />
        <Route path="transactions" element={<AdminTransactionsPage />} />
        <Route path="announcements" element={<AdminAnnouncementsPage />} />
        <Route path="api-keys" element={<AdminApiKeysPage />} />
        <Route path="audit" element={<AdminAuditPage />} />
      </Route>

      <Route
        path="/canvas/:id"
        element={
          <Protected>
            <CanvasPage />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/workspace" replace />} />
    </Routes>
  )
}
