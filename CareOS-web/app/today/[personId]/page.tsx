'use client'
import { use } from 'react'

// The Today screen — spec's primary MVP dashboard. Shows today's doses,
// lets the caregiver tap Taken/Missed, and re-renders with the
// recalculated schedule the backend returns.

import { useEffect, useState } from 'react'

type Dose = {
  id: string
  medication_id: string
  medication_name: string
  scheduled_time_min: number
  actual_time_min: number | null
  status: 'scheduled' | 'taken' | 'missed'
}

type Conflict = { med_a: string; med_b: string; message: string }

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const suffix = h < 12 ? 'AM' : 'PM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${m.toString().padStart(2, '0')} ${suffix}`
}

function nowMinutes(): number {
  const now = new Date()
  return now.getHours() * 60 + now.getMinutes()
}

const API = process.env.NEXT_PUBLIC_API_URL

export default function TodayPage({ params }: { params: Promise<{ personId: string }> }) {
  const { personId } = use(params)
  const [doses, setDoses] = useState<Dose[]>([])
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [infeasible, setInfeasible] = useState(false)
  const [loading, setLoading] = useState(true)

  async function loadToday() {
    setLoading(true)
    const res = await fetch(`${API}/schedule/today/${personId}`)
    const data = await res.json()
    setDoses(data.doses ?? [])
    setLoading(false)
  }

  useEffect(() => {
    loadToday()
  }, [])

  // Every call that touches the scheduling engine can come back
  // feasible:false. When it does, we show the conflict prominently and
  // do NOT silently pretend the schedule updated — the previous,
  // still-consistent schedule stays on screen instead.
  function handleEngineResult(data: { feasible: boolean; conflicts?: Conflict[] }) {
    if (!data.feasible) {
      setInfeasible(true)
      setConflicts(data.conflicts ?? [])
      return false
    }
    setInfeasible(false)
    setConflicts([])
    return true
  }

  async function generateOrRecalculate() {
    const res = await fetch(`${API}/schedule/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId }),
    })
    const data = await res.json()
    handleEngineResult(data)
    loadToday()
  }

  async function markTaken(doseId: string) {
    const res = await fetch(`${API}/doses/${doseId}/taken`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dose_id: doseId, actual_time_min: nowMinutes() }),
    })
    const data = await res.json()
    handleEngineResult(data)
    loadToday() // pulls the recalculated schedule (or the unchanged one, if infeasible)
  }

  async function markMissed(doseId: string) {
    const res = await fetch(`${API}/doses/${doseId}/missed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dose_id: doseId }),
    })
    const data = await res.json()
    handleEngineResult(data)
    loadToday()
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <p className="text-muted-foreground">Loading today's schedule…</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-4xl font-bold text-primary">Today</h1>
        <button onClick={generateOrRecalculate} className="careos-button-secondary">
          Recalculate
        </button>
      </div>

      {infeasible && (
        <div className="careos-card border border-red-200 bg-red-50 mb-6 p-6">
          <p className="font-semibold text-red-700 mb-2">
            ⚠ Couldn't fit a schedule that satisfies every rule.
          </p>
          <p className="text-sm text-red-600 mb-3">
            The previous schedule is still shown below and hasn't been changed. Review these conflicts:
          </p>
          <ul className="space-y-1">
            {conflicts.map((c, i) => (
              <li key={i} className="text-sm text-red-600">• {c.message}</li>
            ))}
          </ul>
        </div>
      )}

      {doses.length === 0 && !infeasible && (
        <div className="careos-card p-10 text-center">
          <p className="text-muted-foreground mb-4">No schedule generated yet for today.</p>
          <button onClick={generateOrRecalculate} className="careos-button">
            Generate Today's Schedule
          </button>
        </div>
      )}

      <div className="space-y-4">
        {doses.map((d) => (
          <div key={d.id} className="careos-card p-5 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="text-lg font-semibold text-primary min-w-[5.5rem]">
                {formatTime(d.actual_time_min ?? d.scheduled_time_min)}
              </div>
              <div>
                <div className="font-medium">{d.medication_name}</div>
                {d.status === 'taken' && (
                  <span className="inline-block mt-1 text-xs font-medium text-green-700 bg-green-100 rounded-full px-3 py-1">
                    ✅ Taken
                  </span>
                )}
                {d.status === 'missed' && (
                  <span className="inline-block mt-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full px-3 py-1">
                    ⚠ Missed
                  </span>
                )}
              </div>
            </div>

            {d.status === 'scheduled' && (
              <div className="flex gap-2">
                <button onClick={() => markTaken(d.id)} className="careos-button">
                  Taken
                </button>
                <button onClick={() => markMissed(d.id)} className="careos-button-secondary">
                  Missed
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}