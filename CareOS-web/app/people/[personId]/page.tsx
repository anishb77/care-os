import { createClient } from '@/lib/supabase/server'
import Link from 'next/link'
import MedicationForm from './medication-form'
import MedRuleForm from './med-rule-form'

export default async function PersonDetailPage({
  params,
}: {
  params: Promise<{ personId: string }>
}) {
  const { personId } = await params
  const supabase = await createClient()

  const { data: person } = await supabase
    .from('people')
    .select('*')
    .eq('id', personId)
    .single()

  const { data: medications } = await supabase
    .from('medications')
    .select('*')
    .eq('person_id', personId)

  const medIds = (medications ?? []).map((m) => m.id)
  const { data: rules } = medIds.length
    ? await supabase.from('med_rules').select('*').in('med_a_id', medIds)
    : { data: [] }

  const medNameById = Object.fromEntries((medications ?? []).map((m) => [m.id, m.name]))

  if (!person) return <p className="p-8 text-muted-foreground">Person not found.</p>

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      <div>
        <h1 className="text-3xl font-semibold text-foreground tracking-tight">{person.name}</h1>
        <Link
          href={`/today/${personId}`}
          className="inline-block mt-3 careos-button"
        >
          View Today's Schedule →
        </Link>
      </div>

      <div className="careos-card p-6">
        <h2 className="text-lg font-semibold mb-4">Medications</h2>
        {medications && medications.length > 0 ? (
          <ul className="space-y-2 mb-6">
            {medications.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between px-4 py-3 rounded-2xl bg-secondary"
              >
                <span className="font-medium">{m.name}</span>
                <span className="text-sm text-muted-foreground">
                  {m.frequency_type.replace('_', ' ')}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mb-6">No medications yet.</p>
        )}
        <MedicationForm personId={personId} />
      </div>

      <div className="careos-card p-6">
        <h2 className="text-lg font-semibold mb-4">Rules Between Medications</h2>
        {rules && rules.length > 0 ? (
          <ul className="space-y-2 mb-6">
            {rules.map((r) => (
              <li
                key={r.id}
                className="px-4 py-3 rounded-2xl bg-secondary text-sm"
              >
                <span className="font-medium">{medNameById[r.med_a_id]}</span>
                {' — '}
                {r.rule_type.replace('_', ' ')}
                {' — '}
                <span className="font-medium">{medNameById[r.med_b_id]}</span>
                {r.min_gap_hours ? ` (${r.min_gap_hours}h)` : ''}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mb-6">No rules yet.</p>
        )}
        <MedRuleForm personId={personId} medications={medications ?? []} />
      </div>
    </div>
  )
}