'use client'

// Add/edit a medication for a person. The important part isn't the form
// fields — it's that every write (insert/update/delete) is immediately
// followed by a call to /schedule/recalculate, so today's schedule never
// silently drifts out of sync with what the caregiver just changed.
//
// If recalculate comes back infeasible (e.g. the new medication's rules
// can't be satisfied alongside the existing ones), we surface that right
// here, next to the form that caused it — not just on the Today screen —
// so the caregiver immediately understands which change caused the problem.

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API = process.env.NEXT_PUBLIC_API_URL

type FrequencyType = 'exact' | 'preferred' | 'window' | 'n_per_day' | 'every_n_hours'

const DAYS = [
  { label: 'Sun', value: 0 },
  { label: 'Mon', value: 1 },
  { label: 'Tue', value: 2 },
  { label: 'Wed', value: 3 },
  { label: 'Thu', value: 4 },
  { label: 'Fri', value: 5 },
  { label: 'Sat', value: 6 },
]

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function minutesToTime(mins: number): string {
  const h = Math.floor(mins / 60).toString().padStart(2, '0')
  const m = (mins % 60).toString().padStart(2, '0')
  return `${h}:${m}`
}

export default function MedicationForm({ personId }: { personId: string }) {
  const [name, setName] = useState('')
  const [frequencyType, setFrequencyType] = useState<FrequencyType>('window')
  const [dosesPerDay, setDosesPerDay] = useState(1)
  const [intervalHours, setIntervalHours] = useState(8)
  const [exactTime, setExactTime] = useState('08:00')
  const [preferredTime, setPreferredTime] = useState('08:00')
  const [windowStart, setWindowStart] = useState('07:00')  // 7:00 AM
  const [windowEnd, setWindowEnd] = useState('21:00')      // 9:00 PM
  const [foodRequirement, setFoodRequirement] = useState('none')

  const [startDate, setStartDate] = useState(todayISO())
  const [isOngoing, setIsOngoing] = useState(true)
  const [endDate, setEndDate] = useState('')
  const [everyDay, setEveryDay] = useState(true)
  const [selectedDays, setSelectedDays] = useState<number[]>([])

  const [saving, setSaving] = useState(false)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)

  function toggleDay(day: number) {
    setSelectedDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort()
    )
  }

  async function recalculateAndCheck() {
    const res = await fetch(`${API}/schedule/recalculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId }),
    })
    const data = await res.json()
    if (!data.feasible) {
      const details = (data.conflicts ?? []).map((c: any) => c.message).join(' ')
      setConflictMessage(
        `This medication couldn't be fit into today's schedule alongside the existing rules. ${details}`
      )
    } else {
      setConflictMessage(null)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setConflictMessage(null)

    const supabase = createClient()
    const { error } = await supabase.from('medications').insert({
      person_id: personId,
      name,
      frequency_type: frequencyType,
      doses_per_day: dosesPerDay,
      interval_hours: frequencyType === 'every_n_hours' ? intervalHours : null,
      exact_time_min: frequencyType === 'exact' ? timeToMinutes(exactTime) : null,
      preferred_time_min: frequencyType === 'preferred' ? timeToMinutes(preferredTime) : null,
      window_start_min: timeToMinutes(windowStart),
      window_end_min: timeToMinutes(windowEnd),
      food_requirement: foodRequirement,
      start_date: startDate,
      end_date: isOngoing ? null : (endDate || null),
      days_of_week: everyDay || selectedDays.length === 0 ? null : selectedDays,
    })

    if (error) {
      setConflictMessage(`Couldn't save: ${error.message}`)
      setSaving(false)
      return
    }

    await recalculateAndCheck()
    setSaving(false)
    setName('')
  }

  const inputClass =
    "block w-full mt-1 px-3 py-2 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
  const labelClass = "text-sm font-medium text-muted-foreground"

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Add Medication</h2>

      <label className={labelClass}>
        Medication name
        <input
          placeholder="Medication name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className={inputClass}
        />
      </label>

      <label className={labelClass}>
        Frequency
        <select
          value={frequencyType}
          onChange={(e) => setFrequencyType(e.target.value as FrequencyType)}
          className={inputClass}
        >
          <option value="exact">Exact time</option>
          <option value="preferred">Preferred time</option>
          <option value="window">Allowed window</option>
          <option value="n_per_day">N times per day</option>
          <option value="every_n_hours">Every N hours</option>
        </select>
      </label>

      {frequencyType === 'exact' && (
        <label className={labelClass}>
          Exact time
          <input
            type="time"
            value={exactTime}
            onChange={(e) => setExactTime(e.target.value)}
            className={inputClass}
          />
        </label>
      )}

      {frequencyType === 'preferred' && (
        <label className={labelClass}>
          Preferred time
          <input
            type="time"
            value={preferredTime}
            onChange={(e) => setPreferredTime(e.target.value)}
            className={inputClass}
          />
        </label>
      )}

      {frequencyType === 'window' && (
        <div className="flex gap-3">
          <label className={`${labelClass} flex-1`}>
            Window start
            <input
              type="time"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={`${labelClass} flex-1`}>
            Window end
            <input
              type="time"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
      )}

      {frequencyType === 'n_per_day' && (
        <>
          <label className={labelClass}>
            How many times per day?
            <input
              type="number"
              min={1}
              max={6}
              value={dosesPerDay}
              onChange={(e) => setDosesPerDay(Number(e.target.value))}
              className={inputClass}
            />
          </label>
          <div className="flex gap-3">
            <label className={`${labelClass} flex-1`}>
              Allowed window start
              <input
                type="time"
                value={windowStart}
                onChange={(e) => setWindowStart(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className={`${labelClass} flex-1`}>
              Allowed window end
              <input
                type="time"
                value={windowEnd}
                onChange={(e) => setWindowEnd(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        </>
      )}

      {frequencyType === 'every_n_hours' && (
        <>
          <label className={labelClass}>
            Every how many hours?
            <input
              type="number"
              min={1}
              max={24}
              value={intervalHours}
              onChange={(e) => setIntervalHours(Number(e.target.value))}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            How many doses total per day?
            <input
              type="number"
              min={1}
              max={6}
              value={dosesPerDay}
              onChange={(e) => setDosesPerDay(Number(e.target.value))}
              className={inputClass}
            />
          </label>
          <div className="flex gap-3">
            <label className={`${labelClass} flex-1`}>
              Allowed window start
              <input
                type="time"
                value={windowStart}
                onChange={(e) => setWindowStart(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className={`${labelClass} flex-1`}>
              Allowed window end
              <input
                type="time"
                value={windowEnd}
                onChange={(e) => setWindowEnd(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        </>
      )}

      <label className={labelClass}>
        Food requirement
        <select
          value={foodRequirement}
          onChange={(e) => setFoodRequirement(e.target.value)}
          className={inputClass}
        >
          <option value="none">No food requirement</option>
          <option value="with">With food</option>
          <option value="without">Without food</option>
          <option value="before">Before food</option>
          <option value="after">After food</option>
        </select>
      </label>

      <div className="rounded-2xl bg-secondary p-4 flex flex-col gap-3">
        <label className={labelClass}>
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={inputClass}
          />
        </label>

        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <input
            type="checkbox"
            checked={isOngoing}
            onChange={(e) => setIsOngoing(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
          />
          This is an ongoing medication (no end date)
        </label>

        {!isOngoing && (
          <label className={labelClass}>
            End date
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputClass}
              required={!isOngoing}
            />
          </label>
        )}
      </div>

      <div className="rounded-2xl bg-secondary p-4 flex flex-col gap-3">
        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <input
            type="checkbox"
            checked={everyDay}
            onChange={(e) => setEveryDay(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
          />
          Every day
        </label>

        {!everyDay && (
          <div className="flex flex-wrap gap-2">
            {DAYS.map((d) => (
              <button
                key={d.value}
                type="button"
                onClick={() => toggleDay(d.value)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  selectedDays.includes(d.value)
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-background text-foreground border border-border'
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <button type="submit" disabled={saving} className="careos-button self-start">
        {saving ? 'Saving…' : 'Add Medication'}
      </button>

      {conflictMessage && (
        <div className="rounded-2xl bg-destructive/10 border border-destructive/30 p-4">
          <strong className="text-destructive">⚠ Schedule conflict</strong>
          <p className="mt-1 text-sm">{conflictMessage}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            The medication was saved, but today's schedule was NOT changed to avoid breaking existing rules. Adjust its window, frequency, or the conflicting rule and it'll recalculate again.
          </p>
        </div>
      )}
    </form>
  )
}