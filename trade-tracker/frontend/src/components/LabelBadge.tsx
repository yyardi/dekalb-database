const COLORS: Record<string, string> = {
  'event-driven': 'bg-purple-900/60 text-purple-300 border-purple-700/50',
  'hedge':        'bg-yellow-900/60 text-yellow-300 border-yellow-700/50',
  'long-term':    'bg-blue-900/60  text-blue-300  border-blue-700/50',
  'short-term':   'bg-orange-900/60 text-orange-300 border-orange-700/50',
  'unclassified': 'bg-gray-800     text-gray-400  border-gray-700',
}

export default function LabelBadge({ label }: { label: string | null }) {
  if (!label) return <span className="text-gray-700 text-xs">—</span>
  const cls = COLORS[label] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded border ${cls} whitespace-nowrap`}>
      {label}
    </span>
  )
}
