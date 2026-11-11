import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Employee search on the main screen, opened with "/" or Ctrl/⌘+K.
export default function GlobalSearch({ platform, onPickEmployee }) {
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [error, setError] = useState('')
  const box = useRef(null)
  const input = useRef(null)

  // Keyboard shortcut to jump to the box.
  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
      if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        input.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Close when clicking elsewhere.
  useEffect(() => {
    const onClick = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  // Ask the API a moment after typing stops.
  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) {
      setResult(null)
      return undefined
    }
    let stale = false
    const t = setTimeout(() => {
      api.search(text)
        .then((r) => { if (!stale) { setResult(r); setActive(0); setError('') } })
        .catch((e) => { if (!stale) setError(e.message) })
    }, 200)
    return () => { stale = true; clearTimeout(t) }
  }, [q])

  const items = result ? result.employees.map((e) => ({ key: `${e.client_id}:${e.code}`, ...e })) : []

  const pick = (item) => {
    onPickEmployee(item.client_id, item.code)
    setOpen(false)
    setQ('')
    input.current?.blur()
  }

  const onKeyDown = (e) => {
    if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
    if (!items.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => (a + 1) % items.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => (a - 1 + items.length) % items.length) }
    if (e.key === 'Enter') { e.preventDefault(); pick(items[active]) }
  }

  const row = (item, i) => (
    <li key={item.key} id={`gs-${i}`} role="option" aria-selected={i === active}
        className={i === active ? 'active' : undefined}
        onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(item) }}>
      <span className="gs-icon" aria-hidden="true">☺</span>
      <span className="gs-text">
        <strong>{item.name}</strong>
        <span className="muted small">{`${item.code}${platform ? ` · ${item.client_name}` : ''}${item.active ? '' : ' · left'}`}</span>
      </span>
    </li>
  )

  const showMenu = open && q.trim().length >= 2

  return (
    <div className="global-search" ref={box}>
      <span className="gs-glass" aria-hidden="true">⌕</span>
      <input
        ref={input}
        type="search"
        value={q}
        placeholder="Search employees by name or code"
        aria-label="Search employees"
        role="combobox"
        aria-expanded={showMenu}
        aria-controls="gs-list"
        aria-activedescendant={showMenu && items.length ? `gs-${active}` : undefined}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      <kbd className="gs-kbd" aria-hidden="true">/</kbd>
      {showMenu && (
        <div className="gs-menu">
          {error && <p className="banner error">{error}</p>}
          {!result && !error && <p className="muted small gs-empty">Searching…</p>}
          {result && items.length === 0 && <p className="muted small gs-empty">No employees match “{result.query}”.</p>}
          <ul id="gs-list" role="listbox" aria-label="Employees found">
            {items.map(row)}
          </ul>
        </div>
      )}
    </div>
  )
}
