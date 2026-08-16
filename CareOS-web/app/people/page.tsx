import { createClient } from '@/lib/supabase/server'
import Link from 'next/link'
import AddPersonForm from './add-person-form'

export default async function PeoplePage() {
  const supabase = await createClient()
  const { data: people, error } = await supabase
    .from('people')
    .select('*')
    .order('created_at', { ascending: false })

  if (error) return <p className="p-8 text-destructive">Error loading people: {error.message}</p>

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      <div>
        <h1 className="text-3xl font-semibold text-foreground tracking-tight">People</h1>
        <p className="text-muted-foreground mt-1">
          Manage the people you care for and their medications.
        </p>
      </div>

      <div className="careos-card p-6">
        <h2 className="text-lg font-semibold mb-4">Your People</h2>
        {people && people.length > 0 ? (
          <ul className="space-y-3 mb-2">
            {people.map((p) => (
              <li
                key={p.id}
                className="flex items-center justify-between px-4 py-4 rounded-2xl bg-secondary"
              >
                <Link
                  href={`/people/${p.id}`}
                  className="font-medium text-foreground hover:text-primary transition-colors"
                >
                  {p.name}
                </Link>
                <Link
                  href={`/today/${p.id}`}
                  className="careos-button-secondary text-sm"
                >
                  Today's Schedule
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No one added yet — add someone below.</p>
        )}
      </div>

      <AddPersonForm />
    </div>
  )
} 