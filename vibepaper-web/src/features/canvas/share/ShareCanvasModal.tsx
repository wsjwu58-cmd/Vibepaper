import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { ShareChoicePanel, type ShareView } from './ShareChoicePanel'
import { ShareLinkPanel } from './ShareLinkPanel'
import { PublishToPaperHubPanel } from './PublishToPaperHubPanel'

export function ShareCanvasModal({
  open,
  onClose,
  canvasId,
  canvasName,
  visibility,
  shareToken,
  onShareMeta,
}: {
  open: boolean
  onClose: () => void
  canvasId: string | number
  canvasName?: string
  visibility?: string
  shareToken?: string
  onShareMeta?: (next: { visibility: string; shareToken?: string }) => void
}) {
  const [view, setView] = useState<ShareView>('choice')
  const [localVisibility, setLocalVisibility] = useState(visibility)
  const [localToken, setLocalToken] = useState(shareToken)

  useEffect(() => {
    if (open) {
      setView('choice')
      setLocalVisibility(visibility)
      setLocalToken(shareToken)
    }
  }, [open, visibility, shareToken])

  const handleClose = () => {
    setView('choice')
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      hideHeader
      size={view === 'paperhub' ? 'lg' : 'md'}
    >
      {view === 'choice' ? (
        <ShareChoicePanel onLink={() => setView('link')} onPaperHub={() => setView('paperhub')} />
      ) : null}
      {view === 'link' ? (
        <ShareLinkPanel
          canvasId={canvasId}
          visibility={localVisibility ?? visibility}
          shareToken={localToken ?? shareToken}
          onBack={() => setView('choice')}
          onUpdated={(next) => {
            setLocalVisibility(next.visibility)
            setLocalToken(next.shareToken)
            onShareMeta?.(next)
          }}
        />
      ) : null}
      {view === 'paperhub' ? (
        <PublishToPaperHubPanel
          canvasId={canvasId}
          defaultTitle={canvasName}
          onBack={() => setView('choice')}
          onDone={handleClose}
        />
      ) : null}
    </Modal>
  )
}
