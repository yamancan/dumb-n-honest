(() => {
  const draft = document.getElementById('draft');
  const description = document.getElementById('description');
  const status = document.getElementById('status');

  async function copy(field) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(field.value);
        status.textContent = 'Copied.';
        return;
      }
    } catch (_) { /* Selection also works when clipboard access is blocked. */ }
    field.focus();
    field.select();
    try {
      if (document.execCommand('copy')) {
        status.textContent = 'Copied.';
        return;
      }
    } catch (_) { /* Keep the visible selection for manual copying. */ }
    status.textContent = 'Text selected. Press ⌘C or Ctrl+C to copy.';
  }

  document.getElementById('copy-draft').addEventListener('click', () => copy(draft));
  document.getElementById('copy-description').addEventListener('click', () => copy(description));
  const providerFilter = document.getElementById('provider-filter');
  const familyFilter = document.getElementById('family-filter');
  const olderModels = document.getElementById('older-models');
  const choices = [...document.querySelectorAll('.model-toggle')];
  const rows = [...document.querySelectorAll('.model')];
  const svgLink = document.getElementById('download-svg');
  const pngButton = document.getElementById('download-png');
  const defaultPngIds = JSON.parse(pngButton.dataset.defaultModels || '[]');
  const decoded = atob(svgLink.dataset.fullChart);
  const fullSVG = decodeURIComponent(Array.from(decoded, byte => '%' + byte.charCodeAt(0).toString(16).padStart(2, '0')).join(''));
  let currentSVG = '';
  let visibleIds = [];

  function filteredSVG(ids) {
    const svg = new DOMParser().parseFromString(fullSVG, 'image/svg+xml').documentElement;
    const selected = new Set(ids);
    for (const model of [...svg.querySelectorAll('[data-model-id]')]) {
      if (!selected.has(model.getAttribute('data-model-id'))) model.remove();
    }
    const models = [...svg.querySelectorAll('[data-model-id]')];
    const maxRate = Math.max(0, ...models.map(model => Number(model.getAttribute('data-owned-rate')) + Number(model.getAttribute('data-conceded-rate')))) || 1;
    let y = 350;
    let providers = 0;
    for (const header of [...svg.querySelectorAll('[data-provider-header]')]) {
      const provider = header.getAttribute('data-provider-header');
      const providerModels = models.filter(model => model.getAttribute('data-provider') === provider);
      if (!providerModels.length) { header.remove(); continue; }
      providers++;
      header.setAttribute('transform', `translate(0 ${y - Number(header.getAttribute('data-base-y'))})`);
      y += 44;
      for (const model of providerModels) {
        model.setAttribute('transform', `translate(0 ${y - Number(model.getAttribute('data-base-y'))})`);
        const ownedWidth = 748 * Number(model.getAttribute('data-owned-rate')) / maxRate;
        const concededWidth = 748 * Number(model.getAttribute('data-conceded-rate')) / maxRate;
        model.querySelector('.bar-owned').setAttribute('width', ownedWidth.toFixed(3));
        model.querySelector('.bar-conceded').setAttribute('width', concededWidth.toFixed(3));
        model.querySelector('.bar-conceded').setAttribute('x', (72 + ownedWidth).toFixed(3));
        y += 110;
      }
    }
    const qualityLines = Number(svg.getAttribute('data-quality-lines'));
    const height = Math.max(1350, 350 + providers * 44 + models.length * 110 + 140 + qualityLines * 24);
    const footer = svg.querySelector('#chart-footer');
    footer.setAttribute('transform', `translate(0 ${height - 110 - qualityLines * 24 - Number(footer.getAttribute('data-base-y'))})`);
    svg.setAttribute('height', height);
    svg.setAttribute('viewBox', `0 0 1080 ${height}`);
    svg.querySelector(':scope > rect').setAttribute('height', height);
    const chartDescription = 'Correction acknowledgments per 100 answered turns. Black is owned error; orange is conceded. Higher is not worse; personal workload, not error rate. '
      + models.map(model => model.getAttribute('data-description')).join(' ')
      + ' ' + footer.textContent;
    svg.querySelector('#description').textContent = chartDescription;
    description.value = chartDescription;
    return new XMLSerializer().serializeToString(svg);
  }

  function applyFilters() {
    const selected = new Set(choices.filter(input => input.checked).map(input => input.value));
    for (const row of rows) {
      const provider = row.closest('.provider').dataset.provider;
      row.hidden = !selected.has(row.dataset.modelId)
        || (!olderModels.checked && row.dataset.recent === '0')
        || (providerFilter.value !== 'all' && providerFilter.value !== provider)
        || (familyFilter.value !== 'all' && familyFilter.value !== row.dataset.family);
    }
    for (const option of document.querySelectorAll('.model-option')) {
      option.hidden = (!olderModels.checked && option.dataset.recent === '0')
        || (providerFilter.value !== 'all' && providerFilter.value !== option.dataset.provider)
        || (familyFilter.value !== 'all' && familyFilter.value !== option.dataset.family);
    }
    for (const section of document.querySelectorAll('.provider')) {
      section.hidden = ![...section.querySelectorAll('.model')].some(row => !row.hidden);
    }
    const visible = rows.filter(row => !row.hidden);
    const maxRate = Math.max(0, ...visible.map(row => Number(row.dataset.ownedRate) + Number(row.dataset.concededRate))) || 1;
    for (const row of visible) {
      row.querySelector('.bar-owned').style.width = (100 * Number(row.dataset.ownedRate) / maxRate) + '%';
      row.querySelector('.bar-conceded').style.width = (100 * Number(row.dataset.concededRate) / maxRate) + '%';
    }
    visibleIds = visible.map(row => row.dataset.modelId);
    document.getElementById('visible-count').textContent = visible.length;
    document.getElementById('empty-models').hidden = visible.length > 0;
    const disabled = visible.length === 0;
    pngButton.setAttribute('aria-disabled', String(disabled));
    svgLink.setAttribute('aria-disabled', String(disabled));
    if ('disabled' in pngButton) pngButton.disabled = disabled;
    currentSVG = filteredSVG(visibleIds);
    svgLink.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(currentSVG);
  }

  providerFilter.addEventListener('change', applyFilters);
  familyFilter.addEventListener('change', applyFilters);
  for (const choice of choices) choice.addEventListener('change', applyFilters);
  olderModels.addEventListener('change', () => {
    for (const choice of choices) {
      if (choice.closest('.model-option').dataset.recent === '0') choice.checked = olderModels.checked;
    }
    applyFilters();
  });
  document.getElementById('select-models').addEventListener('click', () => {
    for (const choice of choices) if (!choice.closest('.model-option').hidden) choice.checked = true;
    applyFilters();
  });
  document.getElementById('clear-models').addEventListener('click', () => {
    for (const choice of choices) choice.checked = false;
    applyFilters();
  });
  svgLink.addEventListener('click', event => { if (!visibleIds.length) event.preventDefault(); });
  pngButton.addEventListener('click', async event => {
    event.preventDefault();
    if (!visibleIds.length) return;
    if (pngButton.dataset.defaultPng && JSON.stringify([...visibleIds].sort()) === JSON.stringify(defaultPngIds)) {
      const link = document.createElement('a');
      link.href = pngButton.dataset.defaultPng;
      link.download = 'dumb-n-honest-chart.png';
      document.body.appendChild(link);
      link.click();
      link.remove();
      status.textContent = 'PNG downloaded for the selected models.';
      return;
    }
    const svg = currentSVG;
    status.textContent = 'Preparing PNG…';
    try {
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
        image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      });
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Canvas unavailable');
      context.drawImage(image, 0, 0);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('PNG unavailable');
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'dumb-n-honest-chart.png';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = 'PNG downloaded for the selected models.';
    } catch (_) {
      status.textContent = 'PNG export was blocked. Download SVG, or use the ready-made chart.png file.';
    }
  });
  applyFilters();
  document.getElementById('save-page').addEventListener('click', () => {
    const page = document.documentElement.cloneNode(true);
    page.querySelector('#draft').textContent = draft.value;
    page.querySelector('#status').textContent = '';
    for (const id of ['provider-filter', 'family-filter']) {
      const select = page.querySelector('#' + id);
      for (const option of select.options) option.toggleAttribute('selected', option.value === document.getElementById(id).value);
    }
    page.querySelector('#older-models').toggleAttribute('checked', olderModels.checked);
    page.querySelector('#description').textContent = description.value;
    for (const input of page.querySelectorAll('.model-toggle')) {
      input.toggleAttribute('checked', choices.find(choice => choice.value === input.value).checked);
    }
    // A textarea's closing tag must remain escaped in the serialized HTML.
    const source = '<!doctype html>\n' + page.outerHTML;
    const url = URL.createObjectURL(new Blob([source], { type: 'text/html;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'dumb-n-honest-report.html';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = 'Page saved with your draft edits.';
  });
})();
