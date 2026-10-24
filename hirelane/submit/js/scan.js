// Scans an application form into a list of fields. Tags each with data-af-id and never changes a value.
() => {
  const clean = (t) => (t || '').replace(/[*\u2731]/g, ' ').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return (r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none') || el.type === 'file';
  };
  const labelOf = (el) => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText; }
    const wrap = el.closest('label'); if (wrap) return wrap.innerText;
    const ids = el.getAttribute('aria-labelledby');
    if (ids) return ids.split(/\s+/).map(i => (document.getElementById(i) || {}).innerText || '').join(' ');
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const box = el.closest('.field, .form-group, .form-field, li, fieldset, div');
    const l = box && box.querySelector('label, legend');
    return l ? l.innerText : (el.getAttribute('placeholder') || el.name || '');
  };
  const optionLabel = (el) => {
    const l = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    return clean(l ? l.innerText : (el.closest('label') ? el.closest('label').innerText : (el.value || '')));
  };
  const groupLabel = (el) => {
    const fs = el.closest('fieldset, [role=group], [role=radiogroup]');
    const lg = fs && (fs.querySelector('legend') || fs.querySelector('[class*=label], [class*=title]'));
    return lg ? lg.innerText : labelOf(el);
  };
  const isRequired = (el, text) => el.required || el.getAttribute('aria-required') === 'true' || /[*\u2731]/.test(text || '');
  const out = []; const seenGroups = new Set(); let n = 0;
  const kindOf = (el) => {
    if (el.tagName === 'TEXTAREA') return 'textarea';
    if (el.tagName === 'SELECT') return 'select';
    if (el.getAttribute('role') === 'combobox') return 'combobox';
    const t = (el.type || 'text').toLowerCase();
    return ({email: 'email', tel: 'tel', url: 'url', number: 'number', date: 'date', file: 'file',
             checkbox: 'checkbox', radio: 'radio', search: 'combobox'})[t] || 'text';
  };
  document.querySelectorAll('input, textarea, select').forEach(el => {
    if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button' || el.name === 'g-recaptcha-response') return;
    if (el.closest('[data-af-skip]')) return;
    if (!visible(el)) return;
    const kind = kindOf(el);
    const fid = 'f' + (n++);
    let label, group = [], options = [], value = '';
    if (kind === 'radio' || (kind === 'checkbox' && el.name && document.querySelectorAll(`input[type=checkbox][name="${CSS.escape(el.name)}"]`).length > 1)) {
      const key = kind + ':' + el.name;
      if (seenGroups.has(key)) { n--; return; }
      seenGroups.add(key);
      group = [...document.querySelectorAll(`input[type=${kind}][name="${CSS.escape(el.name)}"]`)];
      label = groupLabel(el);
      group.forEach((g, i) => { g.setAttribute('data-af-opt', fid + ':' + i); options.push(optionLabel(g)); });
      value = group.filter(g => g.checked).map(g => optionLabel(g)).join(' | ');
      el.setAttribute('data-af-id', fid);
      out.push({fid, label: clean(label), kind: kind === 'radio' ? 'radio' : 'checkboxes', required: group.some(g => isRequired(g, label)), options, value, maxlength: 0});
      return;
    }
    label = kind === 'checkbox' ? (optionLabel(el) || labelOf(el)) : labelOf(el);
    if (kind === 'select') {
      [...el.options].forEach((o, i) => { if (i === 0 && (!o.value || /^select|^choose|^--/i.test(o.text.trim()))) return; options.push(clean(o.text)); });
      value = el.selectedIndex > 0 ? clean(el.options[el.selectedIndex].text) : '';
    } else if (kind === 'checkbox') value = el.checked ? 'checked' : '';
    else if (kind === 'file') value = el.files && el.files.length ? el.files[0].name : '';
    else value = el.value || '';
    el.setAttribute('data-af-id', fid);
    out.push({fid, label: clean(label), kind, required: isRequired(el, label), options, value: value.slice(0, 5000),
              maxlength: el.maxLength > 0 && el.maxLength < 100000 ? el.maxLength : 0});
  });
  return out;
}
