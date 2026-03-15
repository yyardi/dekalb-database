import type { PositionSummary } from '../types'
import LabelBadge from './LabelBadge'

function fmt$(n: number | null) {
  if (n == null) return '—'
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number | null) {
  if (n == null) return '—'
  const v = Number(n)
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

interface Props {
  positions: PositionSummary[]
}

export default function PositionsTable({ positions }: Props) {
  if (!positions.length) {
    return <p className="text-gray-500 text-sm py-4">No open positions.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
            <th className="text-left py-2 pr-4 font-medium">Symbol</th>
            <th className="text-left py-2 pr-4 font-medium">Account</th>
            <th className="text-right py-2 pr-4 font-medium">Qty</th>
            <th className="text-right py-2 pr-4 font-medium">Avg Cost</th>
            <th className="text-right py-2 pr-4 font-medium">Last</th>
            <th className="text-right py-2 pr-4 font-medium">Mkt Value</th>
            <th className="text-right py-2 pr-4 font-medium">Unreal. P&L</th>
            <th className="text-right py-2 pr-4 font-medium">P&L %</th>
            <th className="text-left py-2 font-medium">Label</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => {
            const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null
            const pnlPct = p.unrealized_pnl_pct != null ? Number(p.unrealized_pnl_pct) : null
            const pnlColor =
              pnl == null ? 'text-gray-300' : pnl >= 0 ? 'text-emerald-400' : 'text-red-400'

            return (
              <tr
                key={`${p.account_id}-${p.symbol}-${i}`}
                className="border-b border-gray-800/40 hover:bg-gray-900/60 transition-colors"
              >
                <td className="py-2.5 pr-4 font-semibold text-white">{p.symbol}</td>
                <td className="py-2.5 pr-4 text-gray-500 text-xs">{p.account_id}</td>
                <td className="py-2.5 pr-4 text-right tabular-nums">
                  {Number(p.quantity).toLocaleString()}
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums">
                  {fmt$(p.avg_cost != null ? Number(p.avg_cost) : null)}
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums">
                  {fmt$(p.current_price != null ? Number(p.current_price) : null)}
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums">
                  {fmt$(p.market_value != null ? Number(p.market_value) : null)}
                </td>
                <td className={`py-2.5 pr-4 text-right tabular-nums ${pnlColor}`}>
                  {fmt$(pnl)}
                </td>
                <td className={`py-2.5 pr-4 text-right tabular-nums ${pnlColor}`}>
                  {fmtPct(pnlPct)}
                </td>
                <td className="py-2.5">
                  <LabelBadge label={p.label} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
