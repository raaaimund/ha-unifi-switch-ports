// UniFi Switch Ports card: every switch of a UniFi site drawn like its front
// panel, with link, speed, connected client/device, data rate and PoE per port.
// Served and loaded by the unifi_switch_ports integration; data arrives over
// the websocket subscription unifi_switch_ports/subscribe.
//
//   type: custom:unifi-switch-ports-card
//   entry_id: <config entry>   # optional, defaults to the first UniFi Switch Ports entry
//   show_offline: true         # optional, show switches that are offline
//   show_legend: true          # optional

const SPEEDS = [
  [10000, 's10g', '#8f3bb8', '10G+'],
  [2500, 's2g5', '#1f78c1', '2.5G / 5G'],
  [1000, 's1g', '#299c46', '1G'],
  [100, 's100m', '#e0752d', '100M'],
  [0, 's10m', '#e02f44', '10M'],
];

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const isSfp = (p) => /SFP/i.test(p.media || '');
const speedLabel = (mbps) => (!mbps ? '' : mbps >= 1000 ? `${mbps / 1000}G` : `${mbps}M`);
const speedClass = (mbps) => SPEEDS.find(([min]) => mbps >= min)[1];
const bits = (bytesPerSec, space = ' ') => {
  const b = (Number(bytesPerSec) || 0) * 8;
  for (const [u, f] of [['G', 1e9], ['M', 1e6], ['k', 1e3]]) {
    if (b >= f) {
      return `${(b / f).toFixed(b / f < 10 ? 1 : 0)}${space}${u}bit/s`;
    }
  }
  return `${Math.round(b)}${space}bit/s`;
};

const PORT_WIDTH = 70;
const GAP_WIDTH = 14;

const STYLE = `
:host { display:block; }
ha-card { padding:12px; }
.usp { display:flex; flex-wrap:wrap; gap:12px; }
.usp-switch { border:1px solid var(--divider-color); border-radius:var(--ha-card-border-radius, 12px);
  padding:8px 10px 10px; max-width:100%; box-sizing:border-box; }
.usp-sw-offline { opacity:.5; }
.usp-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 12px; margin-bottom:6px; }
.usp-name { font-weight:600; }
.usp-model, .usp-meta { font-size:12px; color:var(--secondary-text-color); }
.usp-bad { color:var(--error-color); font-weight:600; }
.usp-face { display:grid; gap:6px 4px; padding:8px 10px; border-radius:6px; overflow-x:auto;
  background:var(--secondary-background-color); box-shadow:inset 0 0 0 1px var(--divider-color); }
.usp-port { display:flex; flex-direction:column; align-items:center; cursor:default; min-width:0; }
.usp-jack { position:relative; width:34px; height:30px; box-sizing:border-box; border-radius:2px; background:#2b2e33;
  border:2px solid #5b6068; display:flex; align-items:center; justify-content:center;
  clip-path:polygon(0 0,100% 0,100% 72%,78% 72%,78% 100%,22% 100%,22% 72%,0 72%); }
.usp-sfp .usp-jack { width:44px; height:20px; margin:5px 0; clip-path:none; border-radius:1px; }
.usp-num { font-size:11px; font-weight:600; color:#b8bcc2; margin-top:-5px; }
.usp-sfp .usp-num { margin-top:0; }
.usp-poe { position:absolute; left:1px; top:-1px; font-size:9px; }
.usp-upl { position:absolute; right:2px; top:0; font-size:8px; color:#fff; }
.usp-up .usp-jack { border-color:var(--usp-c); background:var(--usp-c); }
.usp-up .usp-num { color:#fff; }
.usp-disabled .usp-jack { background:repeating-linear-gradient(45deg,#2b2e33,#2b2e33 4px,#5b6068 4px,#5b6068 6px); }
.usp-missing .usp-jack { visibility:hidden; }
${SPEEDS.map(([, cls, color]) => `.${cls} { --usp-c:${color}; }`).join('\n')}
.usp-speed { font-size:11px; font-weight:600; margin-top:3px; line-height:13px; color:var(--usp-c, var(--secondary-text-color)); }
.usp-client { font-size:11px; line-height:13px; width:100%; text-align:center; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.usp-dev-nb { font-weight:600; }
.usp-rate { font-size:10px; line-height:12px; color:var(--secondary-text-color); text-align:center; white-space:nowrap; }
.usp-bar { width:56px; height:3px; margin-top:2px; border-radius:2px; background:var(--divider-color); overflow:hidden; }
.usp-bar i { display:block; height:100%; background:var(--usp-c, transparent); }
.usp-legend, .usp-msg { flex-basis:100%; display:flex; flex-wrap:wrap; gap:4px 14px; font-size:11px; color:var(--secondary-text-color); }
.usp-msg { font-size:14px; }
.usp-legend b { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
`;

class UnifiSwitchPortsCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        { name: 'entry_id', selector: { config_entry: { integration: 'unifi_switch_ports' } } },
        {
          type: 'grid',
          name: '',
          schema: [
            { name: 'show_offline', selector: { boolean: {} } },
            { name: 'show_legend', selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (schema) =>
        ({ entry_id: 'UniFi site', show_offline: 'Show offline switches', show_legend: 'Show legend' })[schema.name],
    };
  }

  static getStubConfig() {
    return { show_offline: true, show_legend: true };
  }

  setConfig(config) {
    const entryChanged = this._config?.entry_id !== config.entry_id;
    this._config = { show_offline: true, show_legend: true, ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' }).innerHTML = `<style>${STYLE}</style><ha-card><div class="usp"></div></ha-card>`;
    }
    if (entryChanged) {
      this._unsubscribe();
      this._subscribe();
    }
    this._draw();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._subscribe();
    }
  }

  connectedCallback() {
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: 'full', min_columns: 6 };
  }

  _subscribe() {
    if (this._unsub || !this._hass || !this._config || !this.isConnected) {
      return;
    }
    const msg = { type: 'unifi_switch_ports/subscribe' };
    if (this._config.entry_id) {
      msg.entry_id = this._config.entry_id;
    }
    this._error = undefined;
    this._unsub = this._hass.connection
      .subscribeMessage((data) => {
        this._data = data;
        this._draw();
      }, msg)
      .catch((err) => {
        this._error = err.message || String(err);
        this._unsub = undefined;
        this._draw();
      });
  }

  _unsubscribe() {
    if (this._unsub) {
      this._unsub.then((unsub) => unsub && unsub()).catch(() => {});
      this._unsub = undefined;
    }
    this._data = undefined;
  }

  _draw() {
    const root = this.shadowRoot?.querySelector('.usp');
    if (root) {
      root.innerHTML = this._render();
    }
  }

  _port(sw, p, idx) {
    if (!p) {
      return '<div class="usp-port usp-missing"><div class="usp-jack"></div></div>';
    }
    const up = sw.online && p.up;
    const speed = p.speed || 0;
    const nb = p.neighbours || [];
    const util = up && speed ? Math.min(1, (Math.max(p.tx_rate || 0, p.rx_rate || 0) * 8) / (speed * 1e6)) : 0;
    const state = !sw.online ? 'usp-offline' : !p.enabled ? 'usp-disabled' : up ? `usp-up ${speedClass(speed)}` : 'usp-down';
    const tip = [
      `${sw.name} · ${p.name} (#${idx}, ${p.media || '?'}${p.combo ? ', combo port' : ''})`,
      !sw.online ? 'Switch offline' : !p.enabled ? 'Disabled' : up ? `Up · ${speedLabel(speed)} ${p.full_duplex ? 'full' : 'half'} duplex` : 'Down',
      p.uplink ? 'Uplink port' : '',
      p.network ? `Network: ${p.network}` : '',
      up ? `To device ↓ ${bits(p.tx_rate)} · from device ↑ ${bits(p.rx_rate)} (${Math.round(util * 100)} %)` : '',
      p.poe_power ? `PoE: ${p.poe_power} W` : '',
      p.sfp_module ? `SFP: ${p.sfp_module}` : isSfp(p) ? 'SFP: empty' : '',
      ...nb.map((n) => `→ ${n.name}${n.detail ? ` (${n.detail})` : ''}`),
    ].filter(Boolean).join('\n');
    const label = nb.length ? nb[0].name + (nb.length > 1 ? ` +${nb.length - 1}` : '') : '';
    return (
      `<div class="usp-port ${isSfp(p) ? 'usp-sfp' : 'usp-rj45'} ${state}" title="${esc(tip)}">` +
      `<div class="usp-jack"><span class="usp-num">${idx}</span>` +
      (p.poe_power ? '<span class="usp-poe">⚡</span>' : '') +
      (p.uplink ? '<span class="usp-upl">▲</span>' : '') +
      `</div>` +
      `<div class="usp-speed">${up ? speedLabel(speed) : !sw.online ? '' : !p.enabled ? 'off' : '–'}</div>` +
      `<div class="usp-client${nb[0]?.device ? ' usp-dev-nb' : ''}">${esc(label) || '&nbsp;'}</div>` +
      `<div class="usp-rate">${up ? `↓${bits(p.tx_rate, '')}<br>↑${bits(p.rx_rate, '')}` : '&nbsp;<br>&nbsp;'}</div>` +
      `<div class="usp-bar"><i style="width:${(util * 100).toFixed(1)}%"></i></div>` +
      `</div>`
    );
  }

  _switch(sw) {
    const byIdx = new Map(sw.ports.map((p) => [p.idx, p]));
    const poe = sw.ports.reduce((s, p) => s + (p.poe_power || 0), 0);
    const tx = sw.ports.filter((p) => !p.uplink).reduce((s, p) => s + (p.tx_rate || 0), 0);
    const meta = sw.online
      ? `${sw.ports_up}/${sw.ports.length} up${poe ? ` · PoE ${poe.toFixed(1)} W` : ''} · ↓ ${bits(tx)} downstream`
      : 'offline';
    // Ubiquiti's diagram rows are aligned column by column; null is a gap.
    const columns = Math.max(...sw.layout.map((row) => row.length));
    const template = Array.from({ length: columns }, (_, i) =>
      sw.layout.every((row) => row[i] == null) ? `${GAP_WIDTH}px` : `${PORT_WIDTH}px`
    ).join(' ');
    const cells = sw.layout
      .map((row, r) =>
        row
          .map((idx, c) =>
            idx == null
              ? ''
              : `<div style="grid-row:${r + 1};grid-column:${c + 1}">${this._port(sw, byIdx.get(idx), idx)}</div>`
          )
          .join('')
      )
      .join('');
    return (
      `<div class="usp-switch${sw.online ? '' : ' usp-sw-offline'}">` +
      `<div class="usp-head"><span class="usp-name">${esc(sw.name)}</span>` +
      `<span class="usp-model">${esc(sw.model_name)}${sw.ip ? ` · ${esc(sw.ip)}` : ''}${sw.version ? ` · ${esc(sw.version)}` : ''}</span>` +
      `<span class="usp-meta${sw.online ? '' : ' usp-bad'}">${esc(meta)}</span></div>` +
      `<div class="usp-face" style="grid-template-columns:${template}">${cells}</div></div>`
    );
  }

  _render() {
    if (this._error) {
      return `<div class="usp-msg">UniFi Switch Ports: ${esc(this._error)}</div>`;
    }
    if (!this._data) {
      return '<div class="usp-msg">Loading…</div>';
    }
    const switches = this._data.switches.filter((sw) => this._config.show_offline || sw.online);
    if (!switches.length) {
      return `<div class="usp-msg">${this._data.available ? 'No switches found.' : `${esc(this._data.title)} is not available.`}</div>`;
    }
    const legend = this._config.show_legend
      ? '<div class="usp-legend">' +
        SPEEDS.map(([, , color, label]) => `<span><b style="background:${color}"></b>${label}</span>`).join('') +
        '<span>⚡ PoE · ▲ uplink · ↓ to device ↑ from device · bar = utilisation · hover a port for details</span></div>'
      : '';
    return switches.map((sw) => this._switch(sw)).join('') + legend;
  }
}

if (!customElements.get('unifi-switch-ports-card')) {
  customElements.define('unifi-switch-ports-card', UnifiSwitchPortsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'unifi-switch-ports-card',
    name: 'UniFi Switch Ports',
    description: 'Ports of your UniFi switches as seen from the front: link, speed, connected device, data rate and PoE.',
    preview: false,
    documentationURL: 'https://github.com/raaaimund/ha-unifi-switch-ports',
  });
}
