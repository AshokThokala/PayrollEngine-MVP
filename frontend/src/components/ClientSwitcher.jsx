import { useEffect, useMemo, useRef, useState } from 'react'

// Top-right client switcher: a button showing the current client that opens a searchable list.
// Keyboard: Enter/Space/Arrow down opens it; arrows move; Enter picks; Escape closes.
export default function ClientSwitcher({ clients, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const box = useRef(null)
  const search = useRef(null)

  const current = clients.find((c) => c.id === value)
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return clients.filter((c) => !q || c.legal_name.toLowerCase().includes(q) || c.id.includes(q))
  }, [clients, query])

  useEffect(() => {
    if (!open) return undefined
    setActive(Math.max(0, matches.findIndex((c) => c.id === value)))
    search.current?.focus()
    const close = (e) => { if (!box.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const pick = (c) => {
    onChange(c.id)
    setOpen(false)
    setQuery('')
  }

  const onKey = (e) => {
    if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, matches.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter' && matches[active]) { e.preventDefault(); pick(matches[active]) }
  }

  return (
    <div className="switcher" ref={box}>
      <button type="button" className="switcher-button" aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}>
        <span className="switcher-initial" aria-hidden="true">{(current?.legal_name || '?').slice(0, 1)}</span>
        <span className="switcher-text">
          <span className="muted small">Client</span>
          <strong>{current ? current.legal_name : 'Choose a client'}</strong>
        </span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="switcher-menu" onKeyDown={onKey}>
          <input ref={search} placeholder="Search clients" value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0) }} aria-label="Search clients" />
          <ul role="listbox" aria-label="Clients">
            {matches.length === 0 && <li className="muted small empty">No matching clients</li>}
            {matches.map((c, i) => (
              <li key={c.id} role="option" aria-selected={c.id === value}
                className={`${i === active ? 'active' : ''} ${c.id === value ? 'current' : ''}`}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(c) }}>
                <span>{c.legal_name}</span>
                <span className="muted small">{c.id} · {c.state}</span>
              </li>
            ))}
          </ul>
          <div className="muted small switcher-count">{clients.length} client{clients.length === 1 ? '' : 's'}</div>
        </div>
      )}
    </div>
  )
}
