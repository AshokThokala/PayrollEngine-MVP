// Small "i" icon that shows help text on hover or keyboard focus.
export default function InfoTip({ id, text }) {
  if (!text) return null
  return (
    <span className="info-tip" tabIndex={0} aria-label="More information">
      i
      <span role="tooltip" id={id} className="info-tip-text">{text}</span>
    </span>
  )
}
