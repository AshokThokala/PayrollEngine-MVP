import { useEffect, useRef, useState } from 'react'

// Marks the part of `text` that matches the search, e.g. "Acme <mark>Tex</mark>tiles".
export function Highlight({ text, q }) {
  const s = String(text ?? '')
  const i = q ? s.toLowerCase().indexOf(q) : -1
  if (i < 0) return s
  return <>{s.slice(0, i)}<mark>{s.slice(i, i + q.length)}</mark>{s.slice(i + q.length)}</>
}

// A search box that suggests matches as you type. Arrow keys + Enter, or click, to pick one.
// `render(item, q)` draws one suggestion; use <Highlight text=... q={q} /> to mark the match.
export default function PickerSearch({ items, match, render, onPick, placeholder, label, limit = 8, autoFocus }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef(null)

  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const text = q.trim().toLowerCase()
  const all = text ? items.filter((it) => match(it, text)) : []
  const results = all.slice(0, limit)
  const more = all.length - results.length

  const pick = (it) => {
    onPick(it)
    setQ('')
    setOpen(false)
  }
  const onKey = (e) => {
    if (e.key === 'Escape') setOpen(false)
    if (!results.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => (a + 1) % results.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => (a - 1 + results.length) % results.length) }
    if (e.key === 'Enter' && open) { e.preventDefault(); pick(results[active]) }
  }

  return (
    <div className="picker" ref={box}>
      <span className="gs-glass" aria-hidden="true">⌕</span>
      <input type="search" value={q} placeholder={placeholder} aria-label={label} autoFocus={autoFocus}
        role="combobox" aria-expanded={open} aria-autocomplete="list"
        onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0) }}
        onFocus={() => setOpen(true)} onKeyDown={onKey} />
      {open && (
        <div className="gs-menu" role="listbox">
          {!text ? (
            <p className="muted small gs-empty">{items.length ? `Start typing to see suggestions (${items.length} to search).` : 'Nothing here yet.'}</p>
          ) : results.length === 0 ? <p className="muted small gs-empty">No matches for “{q.trim()}”.</p> : (
            <ul>
              {results.map((it, i) => (
                <li key={i} role="option" aria-selected={i === active} className={i === active ? 'active' : undefined}
                    onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(it) }}>
                  {render(it, text)}
                </li>
              ))}
            </ul>
          )}
          {more > 0 && <p className="muted small gs-empty">{more} more — keep typing to narrow down.</p>}
        </div>
      )}
    </div>
  )
}
