'use client'

import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

export default function DeleteMedicationButton({
  medicationId,
  personId,
}: {
  medicationId: string
  personId: string
}) {
  const [deleting, setDeleting] = useState(false)
  const router = useRouter()

  async function handleDelete() {
    if (!confirm('Delete this medication? This cannot be undone.')) return
    setDeleting(true)

    const supabase = createClient()
    const { error } = await supabase.from('medications').delete().eq('id', medicationId)

    if (error) {
      alert(`Couldn't delete: ${error.message}`)
      setDeleting(false)
      return
    }

    // Same pattern as every other write in this app: recalculate today's
    // schedule immediately after, since removing a medication can free up
    // room for others or leave the day empty.
    await fetch(`${API}/schedule/recalculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId }),
    })

    router.refresh()
  }

  return (
    <button
      onClick={handleDelete}
      disabled={deleting}
      className="text-sm font-medium text-destructive hover:underline disabled:opacity-50"
    >
      {deleting ? 'Deleting…' : 'Delete'}
    </button>
  )
}
