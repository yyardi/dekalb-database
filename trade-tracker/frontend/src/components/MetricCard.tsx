interface MetricCardProps {
  label: string
  value: string | null
  subValue?: string | null
  /** true = green, false = red, null/undefined = white (neutral) */
  positive?: boolean | null
}

export default function MetricCard({ label, value, subValue, positive }: MetricCardProps) {
  const valueColor =
    positive == null
      ? 'text-white'
      : positive
      ? 'text-emerald-400'
      : 'text-red-400'

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${valueColor}`}>{value ?? '—'}</p>
      {subValue != null && (
        <p className="text-xs text-gray-500 mt-1">{subValue}</p>
      )}
    </div>
  )
}
