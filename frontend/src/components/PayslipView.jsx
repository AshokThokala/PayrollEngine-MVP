import { money } from '../api.js'

// Earnings, deductions and employer contributions for one payslip.
function Lines({ title, lines }) {
  return (
    <div>
      <h4>{title}</h4>
      {lines.length === 0 ? <p className="muted small">None</p> : (
        <table className="compact">
          <tbody>
            {lines.map((l) => (
              <tr key={l.code} title={l.rule || ''}>
                <td>{l.label}</td>
                <td className="num">{money(l.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function PayslipView({ slip }) {
  return (
    <div className="payslip">
      <Lines title="Earnings" lines={slip.earnings} />
      <Lines title="Deductions" lines={slip.deductions} />
      <Lines title="Employer contributions" lines={slip.employer_contributions} />
      <p className="muted small">
        Statutory wages (Code on Wages): {money(slip.statutory_wages)}. Hover a line to see the rule version used.
        {slip.warnings.length > 0 && ` Warnings: ${slip.warnings.join(' ')}`}
      </p>
    </div>
  )
}
