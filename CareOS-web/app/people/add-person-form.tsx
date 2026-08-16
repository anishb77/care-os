'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useRouter } from 'next/navigation'

function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export default function AddPersonForm() {
  const [name, setName] = useState('')
  const [wakeTime, setWakeTime] = useState('07:00')
  const [sleepTime, setSleepTime] = useState('22:00')
  const [breakfastTime, setBreakfastTime] = useState('08:00')
  const [lunchTime, setLunchTime] = useState('12:00')
  const [dinnerTime, setDinnerTime] = useState('18:00')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)

    const supabase = createClient()
    const { data: { user } } = await supabase.auth.getUser()

    if (!user) {
      setError('You must be logged in.')
      setSaving(false)
      return
    }

    const { error: insertError } = await supabase.from('people').insert({
      caregiver_id: user.id,
      name,
      wake_time_min: timeToMinutes(wakeTime),
      sleep_time_min: timeToMinutes(sleepTime),
      breakfast_time_min: timeToMinutes(breakfastTime),
      lunch_time_min: timeToMinutes(lunchTime),
      dinner_time_min: timeToMinutes(dinnerTime),
    })

    if (insertError) {
      setError(insertError.message)
      setSaving(false)
      return
    }

    setName('')
    setSaving(false)
    router.refresh()
  }

  const inputClass =
    "block w-full mt-1 px-3 py-2 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"

  return (
    <form onSubmit={handleSubmit} className="careos-card p-6 flex flex-col gap-4 max-w-sm">
      <h2 className="text-lg font-semibold">Add Person</h2>

      <label className="text-sm font-medium text-muted-foreground">
        Name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className={inputClass}
        />
      </label>

      <label className="text-sm font-medium text-muted-foreground">
        Wake time
        <input
          type="time"
          value={wakeTime}
          onChange={(e) => setWakeTime(e.target.value)}
          className={inputClass}
        />
      </label>

      <label className="text-sm font-medium text-muted-foreground">
        Sleep time
        <input
          type="time"
          value={sleepTime}
          onChange={(e) => setSleepTime(e.target.value)}
          className={inputClass}
        />
      </label>

      <label className="text-sm font-medium text-muted-foreground">
        Breakfast time
        <input
          type="time"
          value={breakfastTime}
          onChange={(e) => setBreakfastTime(e.target.value)}
          className={inputClass}
        />
      </label>

      <label className="text-sm font-medium text-muted-foreground">
        Lunch time
        <input
          type="time"
          value={lunchTime}
          onChange={(e) => setLunchTime(e.target.value)}
          className={inputClass}
        />
      </label>

      <label className="text-sm font-medium text-muted-foreground">
        Dinner time
        <input
          type="time"
          value={dinnerTime}
          onChange={(e) => setDinnerTime(e.target.value)}
          className={inputClass}
        />
      </label>

      <button type="submit" disabled={saving} className="careos-button mt-2">
        {saving ? 'Saving…' : 'Add Person'}
      </button>

      {error && <p className="text-destructive text-sm">{error}</p>}
    </form>
  )
}