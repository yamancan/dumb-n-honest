const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(0, 'utf8');
const dom = new JSDOM(html, { runScripts: 'dangerously' });
const { document, Event, DOMParser } = dom.window;
const visible = () => [...document.querySelectorAll('.model')].filter(row => !row.hidden).map(row => row.dataset.modelId);
const change = (id, value) => {
  const field = document.getElementById(id);
  if (typeof value === 'boolean') field.checked = value;
  else field.value = value;
  field.dispatchEvent(new Event('change', { bubbles: true }));
};

assert(!visible().includes('gpt-5.3-codex-spark'), 'Old generation should start hidden');
change('family-filter', 'sol');
assert.deepEqual(visible().sort(), ['gpt-5.6-sol', 'gpt-6-sol', 'gpt-6.1-sol'].sort(), 'Family filter should isolate Sol versions');
change('family-filter', 'all');
change('provider-filter', 'claude');
assert(visible().every(id => id.startsWith('claude-')), 'Provider filter should isolate Claude');
change('provider-filter', 'all');
change('older-models', true);
assert(visible().includes('gpt-5.3-codex-spark'), 'Older generations should be available explicitly');
document.getElementById('clear-models').click();
assert.equal(visible().length, 0, 'Clear should hide all models');
assert.equal(document.getElementById('download-png').getAttribute('aria-disabled'), 'true', 'Empty chart should not be downloaded');
const solo = [...document.querySelectorAll('.model-toggle')].find(input => input.value === 'gpt-6.1-sol');
solo.checked = true;
solo.dispatchEvent(new Event('change', { bubbles: true }));
assert.deepEqual(visible(), ['gpt-6.1-sol'], 'Individual model selection should isolate one version');
const link = document.getElementById('download-svg').href;
const source = link.startsWith('data:image/svg+xml;base64,')
  ? Buffer.from(link.split(',')[1], 'base64').toString('utf8')
  : decodeURIComponent(link.split(',')[1]);
const svg = new DOMParser().parseFromString(source, 'image/svg+xml');
assert.deepEqual([...svg.querySelectorAll('[data-model-id]')].map(row => row.getAttribute('data-model-id')), ['gpt-6.1-sol'], 'SVG export should contain only selected models');
assert(!svg.querySelector('#description').textContent.includes('Claude'), 'Export description should match the selected chart');
assert.equal(document.getElementById('visible-count').textContent, '1');
dom.window.close();
console.log('Workspace family, provider, old-generation, individual-model and SVG-export filters passed.');
