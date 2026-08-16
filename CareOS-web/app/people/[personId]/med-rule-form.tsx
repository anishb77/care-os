'use client'

// Adds caregiver-defined rules BETWEEN medications. Flow: pick one
// medication, check off which OTHER medications it has a rule with, and
// configure each checked rule inline. Submitting saves all checked rules
// at once. Never auto-populated from any external source — every rule
// here is something the caregiver explicitly entered (spec section 9).

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API = process.env.NEXT_PUBLIC_API_URL

type Medication = { id: string; name: string }
type RuleType = 'before' | 'after' | 'min_separation'

type RuleConfig = {
  checked: boolean
  ruleType: RuleType
  minGapHours: number
}

export default function MedRuleForm({
  personId,
  medications,
}: {
  personId: string
  medications: Medication[]
}) {
  const [primaryMedId, setPrimaryMedId] = useState('')
  const [configs, setConfigs] = useState<Record<string, RuleConfig>>({})

  const [saving, setSaving] = useState(false)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)

  const otherMeds = medications.filter((m) => m.id !== primaryMedId)

  function toggleMed(medId: string, checked: boolean) {
    setConfigs((prev) => ({
      ...prev,
      [medId]: checked
        ? { checked: true, ruleType: prev[medId]?.ruleType ?? 'min_separation', minGapHours: prev[medId]?.minGapHours ?? 2 }
        : { ...prev[medId], checked: false },
    }))
  }

  function updateConfig(medId: string, patch: Partial<RuleConfig>) {
    setConfigs((prev) => ({
      ...prev,
      [medId]: { ...prev[medId], ...patch },
    }))
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
      setConflictMessage(`These rules couldn't be fit into today's schedule. ${details}`)
    } else {
      setConflictMessage(null)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!primaryMedId) {
      setConflictMessage('Choose a medication first.')
      return
    }

    const checkedEntries = Object.entries(configs).filter(([, c]) => c.checked)
    if (checkedEntries.length === 0) {
      setConflictMessage('Check at least one related medication.')
      return
    }

    setSaving(true)
    setConflictMessage(null)

    const supabase = createClient()
    const rows = checkedEntries.map(([medBId, c]) => ({
      med_a_id: primaryMedId,
      med_b_id: medBId,
      rule_type: c.ruleType,
      min_gap_hours: c.minGapHours,
    }))

    const { error } = await supabase.from('med_rules').insert(rows)

    if (error) {
      setConflictMessage(`Couldn't save: ${error.message}`)
      setSaving(false)
      return
    }

    setConfigs({})
    await recalculateAndCheck()
    setSaving(false)
  }

  if (medications.length < 2) {
    return <p style={{ color: '#666' }}>Add at least 2 medications to set a rule between them.</p>
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: '1rem' }}>
      <h3>Add Rules for a Medication</h3>

      <label>
        Which medication?
        <select
          value={primaryMedId}
          onChange={(e) => { setPrimaryMedId(e.target.value); setConfigs({}) }}
          style={{ display: 'block' }}
        >
          <option value="">— choose —</option>
          {medications.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
      </label>

      {primaryMedId && (
        <div style={{ marginTop: '1rem' }}>
          <p>Check any medications that have a rule with this one:</p>
          {otherMeds.map((m) => {
            const config = configs[m.id]
            return (
              <div key={m.id} style={{ marginBottom: '0.75rem', paddingLeft: '0.5rem', borderLeft: '2px solid #ddd' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input
                    type="checkbox"
                    checked={config?.checked ?? false}
                    onChange={(e) => toggleMed(m.id, e.target.checked)}
                  />
                  {m.name}
                </label>

                {config?.checked && (
                  <div style={{ marginLeft: '1.5rem', marginTop: '0.5rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <select
                      value={config.ruleType}
                      onChange={(e) => updateConfig(m.id, { ruleType: e.target.value as RuleType })}
                    >
                      <option value="min_separation">at least __ hrs apart</option>
                      <option value="before">must be before</option>
                      <option value="after">must be after</option>
                    </select>
                    {config.ruleType === 'min_separation' && (
                      <input
                        type="number"
                        min={0}
                        step={0.5}
                        value={config.minGapHours}
                        onChange={(e) => updateConfig(m.id, { minGapHours: Number(e.target.value) })}
                        style={{ width: '4rem' }}
                      />
                    )}
                    {config.ruleType === 'min_separation' && 'hours'}
                  </div>
                )}
              </div>
            )
          })}

          <button type="submit" disabled={saving} style={{ marginTop: '0.5rem' }}>
            {saving ? 'Saving…' : 'Save Rules'}
          </button>
        </div>
      )}

      {conflictMessage && (
        <div style={{ background: '#fde2e2', border: '1px solid #e57373', padding: '1rem', marginTop: '1rem' }}>
          <strong>⚠ Schedule conflict</strong>
          <p>{conflictMessage}</p>
        </div>
      )}
    </form>
  )
}