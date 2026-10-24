// Visible validation errors on the page.
() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const found = [];
  document.querySelectorAll('[role=alert], [class*=error], .invalid-feedback, [id$=-error], [id$=_error]').forEach(e => {
    const t = (e.innerText || '').trim();
    if (t && t.length < 200 && vis(e) && /required|invalid|please (enter|select|fill|complete|provide)|can.?t be blank|must be/i.test(t)) found.push(t);
  });
  document.querySelectorAll('[aria-invalid=true]').forEach(e => { if (vis(e)) found.push('invalid field: ' + (e.name || e.id || 'unnamed')); });
  return [...new Set(found)].slice(0, 8);
}
