// ==UserScript==
// @name         Ai Là Vua Lì Đòn (EMB V5.7)
// @namespace    http://tampermonkey.net/
// @version      5.7
// @description  3 chế độ gửi dữ liệu: 1) Clipboard (không cần host) 2) WebSocket 3) HTTP. Tự động chọn kênh tốt nhất. Tự động tìm & tải ảnh.
// @author       Antigravity
// @match        https://portal.godgroup.com/design/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_setClipboard
// ==/UserScript==

(function () {
    'use strict';

    // ── CONFIG ────────────────────────────────────────────────────────────────
    const DEFAULT_HOST   = "http://127.0.0.1:5000";
    const DEFAULT_WS     = "ws://127.0.0.1:5001";
    const RECEIVE_PATH   = "/receive";
    const WS_INFO_PATH   = "/ws_info";
    const PING_INTERVAL  = 10000;
    const CLIP_MARKER    = "TX_EMB::";          // Must match clipboard_bridge.py MARKER
    const PROCESSED_ATTR = "data-tx-done";
    const STORAGE_HOST   = "emb_host";
    const STORAGE_ON     = "emb_enabled";
    const STORAGE_MODE   = "emb_mode";         // "clipboard" | "websocket" | "http"

    // ── STATE ─────────────────────────────────────────────────────────────────
    let host      = GM_getValue(STORAGE_HOST, DEFAULT_HOST).replace(/\/+$/, '');
    let mode      = GM_getValue(STORAGE_MODE, 'websocket'); // default: websocket
    let enabled   = GM_getValue(STORAGE_ON, true);
    let sentCount = 0;
    let pingTimer = null;
    let connState = 'idle';
    let ws        = null;
    let wsConn    = false;

    const MODE_LABELS = {
        clipboard: '📋 Clipboard',
        websocket: '⚡ WebSocket',
        http:      '🌐 HTTP'
    };

    function getUrl(p) { return host + p; }

    // ── STYLES ────────────────────────────────────────────────────────────────
    const css = document.createElement('style');
    css.textContent = `
        .tx-btn{background:#ff003c;color:#fff;border:none;padding:2px 6px;font-size:10px;
            font-weight:bold;border-radius:3px;cursor:pointer;margin-right:8px;display:inline-block;vertical-align:middle}
        .tx-btn:hover{background:#ff4466}
        #emb-wrap{position:fixed;bottom:16px;right:16px;z-index:999999;font-family:monospace;user-select:none}
        #emb-panel{background:#111;color:#eee;border:1px solid #2a2a2a;border-radius:8px;
            width:240px;box-shadow:0 4px 20px rgba(0,0,0,.6)}
        #emb-hdr{background:#0d0d0d;padding:6px 10px;display:flex;align-items:center;
            gap:6px;cursor:move;border-radius:8px 8px 0 0;border-bottom:1px solid #222}
        #emb-hdr-title{flex:1;font-weight:bold;color:#ff003c;font-size:11px;letter-spacing:.5px}
        #emb-hdr button{background:none;border:none;color:#555;cursor:pointer;font-size:13px;padding:0 2px}
        #emb-hdr button:hover{color:#eee}
        #emb-body{padding:8px 10px;display:flex;flex-direction:column;gap:5px}

        /* Mode selector pills */
        #emb-mode-row{display:flex;gap:3px}
        .emb-mode-btn{flex:1;padding:3px 0;border-radius:4px;border:1px solid #333;
            background:#1a1a1a;color:#666;cursor:pointer;font-size:9px;font-family:monospace;
            transition:all .15s;text-align:center}
        .emb-mode-btn:hover{background:#252525;color:#ccc}
        .emb-mode-btn.active-clip{border-color:#ff9900;background:#1a1000;color:#ff9900}
        .emb-mode-btn.active-ws  {border-color:#00cc44;background:#001a08;color:#00cc44}
        .emb-mode-btn.active-http{border-color:#4499ff;background:#00081a;color:#4499ff}

        #emb-conn-row{display:flex;align-items:center;gap:6px;cursor:pointer;
            padding:3px 4px;border-radius:4px;transition:background .2s}
        #emb-conn-row:hover{background:#1a1a1a}
        #emb-dot{width:8px;height:8px;border-radius:50%;background:#555;flex-shrink:0;transition:background .3s}
        #emb-conn-label{font-size:10px;font-weight:bold;color:#555;transition:color .3s;flex:1}
        #emb-ping-ms{font-size:10px;color:#444}
        #emb-conn-hint{font-size:9px;color:#2a2a2a;text-align:center}

        #emb-clip-box{background:#0d0d0d;border:1px solid #2a1a00;border-radius:4px;padding:5px 8px;
            display:none}
        #emb-clip-box.visible{display:block}
        #emb-clip-title{font-size:9px;color:#886600;margin-bottom:1px}
        #emb-clip-desc{font-size:10px;color:#cc9900;line-height:1.4}

        #emb-app-box{background:#0d0d0d;border:1px solid #222;border-radius:4px;padding:4px 8px;
            transition:border-color .3s,background .3s}
        #emb-app-label{font-size:9px;color:#444;margin-bottom:1px}
        #emb-app-name{font-size:11px;color:#555;transition:color .3s}

        #emb-host-box{background:#0d0d0d;border:1px solid #2a2a2a;border-radius:4px;padding:4px 8px}
        #emb-host-label{font-size:9px;color:#444;margin-bottom:1px}
        #emb-host-val{font-size:11px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        #emb-host-input{display:none;width:100%;box-sizing:border-box;background:#0d0d0d;
            border:1px solid #555;border-radius:4px;color:#0f0;font-size:11px;
            padding:4px 8px;font-family:monospace;outline:none}
        #emb-host-input:focus{border-color:#ff003c}

        .emb-row{display:flex;gap:4px}
        .emb-row button{flex:1;padding:3px 0;border-radius:4px;border:1px solid #333;
            background:#1a1a1a;color:#888;cursor:pointer;font-size:10px;font-family:monospace;
            transition:background .15s,color .15s}
        .emb-row button:hover{background:#2a2a2a;color:#eee}
        .emb-row button.on{border-color:#1a3a1a;background:#0a1a0a;color:#00cc44}
        .emb-row button.off{border-color:#333;background:#1a1a1a;color:#555}
        .emb-row button.danger{border-color:#cc2200;color:#ff4422;background:transparent}
        .emb-row button.danger:hover{background:#1a0500}
        .emb-row button.accent{border-color:#ff003c;color:#ff003c;background:transparent}
        .emb-row button.accent:hover{background:#1a0010}

        #emb-status{font-size:10px;color:#444;text-align:center;min-height:13px;transition:color .3s}
        #emb-status.ok{color:#00cc44} #emb-status.err{color:#ff4422} #emb-status.warn{color:#ff9900}
        #emb-min{display:block;position:fixed;bottom:16px;right:16px;
            background:#ff003c;color:#fff;border:none;border-radius:6px;
            padding:5px 10px;font-size:11px;font-weight:bold;font-family:monospace;
            cursor:pointer;z-index:999999;box-shadow:0 2px 8px rgba(0,0,0,.5)}
        #emb-min:hover{background:#ff4466}
    `;
    document.head.appendChild(css);

    // ── PANEL DOM ─────────────────────────────────────────────────────────────
    const wrap = document.createElement('div'); wrap.id = 'emb-wrap';
    wrap.innerHTML = `
        <div id="emb-panel" style="display:none">
            <div id="emb-hdr">
                <span id="emb-hdr-title">Ai Là Vua Lì Đòn</span>
                <button id="emb-btn-min" title="Thu gọn">–</button>
            </div>
            <div id="emb-body">
                <!-- Mode selector -->
                <div id="emb-mode-row">
                    <button class="emb-mode-btn" data-mode="clipboard" title="Không cần host — copy vào clipboard">📋</button>
                    <button class="emb-mode-btn" data-mode="websocket" title="WebSocket realtime">⚡ WS</button>
                    <button class="emb-mode-btn" data-mode="http"      title="HTTP POST truyền thống">🌐 HTTP</button>
                </div>

                <!-- Clipboard info box -->
                <div id="emb-clip-box">
                    <div id="emb-clip-title">📋 Chế độ Clipboard (không cần host)</div>
                    <div id="emb-clip-desc">Dữ liệu được copy vào clipboard.<br>Python app tự đọc và xử lý.</div>
                </div>

                <!-- Connection status (shown in WS/HTTP mode) -->
                <div id="emb-conn-row" title="Double-click để sửa host">
                    <div id="emb-dot"></div>
                    <span id="emb-conn-label">—</span>
                    <span id="emb-ping-ms"></span>
                </div>
                <div id="emb-conn-hint">⬆ Double-click để sửa host thủ công</div>

                <div id="emb-app-box">
                    <div id="emb-app-label">Ứng dụng</div>
                    <div id="emb-app-name">—</div>
                </div>
                <div id="emb-host-box">
                    <div id="emb-host-label">Host</div>
                    <div id="emb-host-val"></div>
                    <input id="emb-host-input" type="text" placeholder="http://127.0.0.1:5000"/>
                </div>
                <div class="emb-row">
                    <button id="emb-btn-toggle"></button>
                    <button id="emb-btn-edit">✎ Edit</button>
                    <button id="emb-btn-save" style="display:none">✓ Save</button>
                    <button id="emb-btn-reset">⟳</button>
                </div>
                <div id="emb-status"></div>
            </div>
        </div>
    `;
    document.body.appendChild(wrap);
    const minBtn = document.createElement('button'); minBtn.id = 'emb-min'; minBtn.textContent = '▲ Vua Lì Đòn';
    document.body.appendChild(minBtn);

    // ── REFS ──────────────────────────────────────────────────────────────────
    const panel      = wrap.querySelector('#emb-panel');
    const dot        = wrap.querySelector('#emb-dot');
    const connLabel  = wrap.querySelector('#emb-conn-label');
    const connRow    = wrap.querySelector('#emb-conn-row');
    const connHint   = wrap.querySelector('#emb-conn-hint');
    const pingMs     = wrap.querySelector('#emb-ping-ms');
    const clipBox    = wrap.querySelector('#emb-clip-box');
    const appName    = wrap.querySelector('#emb-app-name');
    const appBox     = wrap.querySelector('#emb-app-box');
    const hostVal    = wrap.querySelector('#emb-host-val');
    const hostInput  = wrap.querySelector('#emb-host-input');
    const btnToggle  = wrap.querySelector('#emb-btn-toggle');
    const btnEdit    = wrap.querySelector('#emb-btn-edit');
    const btnSave    = wrap.querySelector('#emb-btn-save');
    const btnReset   = wrap.querySelector('#emb-btn-reset');
    const btnMin     = wrap.querySelector('#emb-btn-min');
    const statusEl   = wrap.querySelector('#emb-status');
    const modeBtns   = [...wrap.querySelectorAll('.emb-mode-btn')];

    // ── HELPERS ───────────────────────────────────────────────────────────────
    function setStatus(msg, type, ms) {
        statusEl.textContent = msg; statusEl.className = type || '';
        if (ms !== 0) setTimeout(() => { statusEl.textContent = ''; statusEl.className = ''; }, ms || 2500);
    }

    function renderMode() {
        const isClip = mode === 'clipboard';
        clipBox.classList.toggle('visible', isClip);
        connRow.style.display    = isClip ? 'none' : '';
        connHint.style.display   = isClip ? 'none' : '';
        appBox.style.display     = isClip ? 'none' : '';
        wrap.querySelector('#emb-host-box').style.display = isClip ? 'none' : '';
        btnEdit.style.display    = isClip ? 'none' : '';
        btnReset.style.display   = isClip ? 'none' : '';

        modeBtns.forEach(b => {
            b.className = 'emb-mode-btn';
            if (b.dataset.mode === mode) {
                b.classList.add('active-' + mode);
            }
        });
    }

    function applyConnState(state, appText, latency) {
        connState = state;
        const cfg = {
            ok:   { dot:'#00cc44', label: wsConn ? '⚡ WebSocket' : '🌐 HTTP', lc:'#00cc44' },
            err:  { dot:'#ff4422', label:'Mất kết nối',  lc:'#ff4422' },
            idle: { dot:'#555',    label:'Chưa kết nối', lc:'#555'   }
        }[state] || {};
        dot.style.background = cfg.dot;
        connLabel.style.color = cfg.lc;
        connLabel.textContent = cfg.label;
        pingMs.textContent = latency != null ? `${latency}ms` : '';
        if (state === 'ok') {
            appBox.style.background = '#0a1a0a'; appBox.style.borderColor = '#1a3a1a';
            appName.style.color = '#0f0'; appName.textContent = appText || '—';
        } else if (state === 'err') {
            appBox.style.background = '#1a0800'; appBox.style.borderColor = '#3a1800';
            appName.style.color = '#ff6633'; appName.textContent = 'App offline?';
        } else {
            appBox.style.background = '#0d0d0d'; appBox.style.borderColor = '#222';
            appName.style.color = '#444'; appName.textContent = '—';
        }
    }

    function renderToggle() {
        btnToggle.textContent = enabled ? '● Bật' : '○ Tắt';
        btnToggle.className   = enabled ? 'on' : 'off';
    }

    function renderHost() { hostVal.textContent = host; }

    function showEditMode(on) {
        hostInput.style.display = on ? 'block' : 'none';
        hostVal.style.display   = on ? 'none'  : 'block';
        btnEdit.style.display   = on ? 'none'  : '';
        btnSave.style.display   = on ? ''      : 'none';
        if (on) { hostInput.value = host; hostInput.focus(); hostInput.select(); }
    }

    // Find the design preview image URL on the page
    function findImageUrl(row) {
        // 1. Try to find img with alt="Artwork" in the row or document
        let imgEl = null;
        if (row) {
            imgEl = row.querySelector('img[alt="Artwork"]');
        }
        if (!imgEl) {
            imgEl = document.querySelector('img[alt="Artwork"]');
        }
        if (!imgEl && row) {
            imgEl = row.querySelector('img');
        }
        if (!imgEl) {
            imgEl = document.querySelector('img[src*="designs/"], img[src*="manual"], img.design-preview');
        }

        if (imgEl && imgEl.src) {
            let src = imgEl.src;
            try {
                // If it's a resize service URL, extract the actual full resolution URL
                if (src.includes('url=')) {
                    const urlObj = new URL(src);
                    const actualUrl = urlObj.searchParams.get('url');
                    if (actualUrl) {
                        return decodeURIComponent(actualUrl);
                    }
                }
            } catch(e) {
                console.error("Error parsing image URL:", e);
            }
            return src;
        }

        // 2. Check if there is an <a> link with text "Download Image"
        const clickables = Array.from(document.querySelectorAll('button, a, .text-blue'));
        for (const el of clickables) {
            const txt = el.textContent.trim().toLowerCase();
            if (txt === "download image" || txt.includes("download image")) {
                if (el.tagName === 'A' && el.href) {
                    return el.href;
                }
            }
        }

        return '';
    }

    // Direct browser download simulation
    function triggerBrowserDownload(url, filename) {
        console.log("[TM] Triggering browser Blob download for:", url);
        fetch(url)
            .then(response => response.blob())
            .then(blob => {
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            })
            .catch(err => {
                console.error("[TM] Direct download failed, opening in new tab:", err);
                window.open(url, '_blank');
            });
    }

    // ── WebSocket ─────────────────────────────────────────────────────────────
    function connectWS(url) {
        if (ws) { try { ws.close(); } catch(e){} }
        try {
            ws = new WebSocket(url);
            ws.onopen  = () => { wsConn = true; ws.send(JSON.stringify({test:true})); };
            ws.onmessage = e => {
                try {
                    const d = JSON.parse(e.data);
                    if (d.name) applyConnState('ok', d.name+(d.version?' v'+d.version:''), null);

                    if (d.action === "download_image") {
                        console.log("[WS] Received download_image command from TX App");
                        const clickables = Array.from(document.querySelectorAll('button, a, .text-blue'));
                        let found = false;
                        for (const el of clickables) {
                            const txt = el.textContent.trim().toLowerCase();
                            if (txt === "download image" || txt.includes("download image")) {
                                console.log("[WS] Simulating click on:", el);
                                el.click();
                                found = true;
                                break;
                            }
                        }
                        if (!found) {
                            console.warn("[WS] Could not find any button/link with text 'Download Image'. Trying to find image element...");
                            const imgUrl = findImageUrl(null);
                            if (imgUrl) {
                                console.log("[WS] Found image URL, triggering download:", imgUrl);
                                triggerBrowserDownload(imgUrl, "1.png");
                                found = true;
                            } else {
                                console.error("[WS] No image URL found on page.");
                            }
                        }
                    }
                } catch(err){}
            };
            ws.onclose = () => { wsConn = false; };
            ws.onerror = () => { wsConn = false; };
        } catch(e) { wsConn = false; }
    }

    // ── Ping (WS/HTTP mode) ───────────────────────────────────────────────────
    function ping() {
        if (!enabled || mode === 'clipboard') return;
        const t0 = Date.now();
        GM_xmlhttpRequest({
            method:'GET', url: getUrl(WS_INFO_PATH), timeout:3000,
            onload(r) {
                const ms = Date.now()-t0;
                try {
                    const d = JSON.parse(r.responseText);
                    if (mode==='websocket' && d.ws_url && !wsConn) connectWS(d.ws_url);
                    applyConnState('ok', (d.name||'OK')+(d.version?' v'+d.version:''), ms);
                } catch { applyConnState('ok','Kết nối OK', ms); }
            },
            onerror()  { applyConnState('err'); },
            ontimeout(){ applyConnState('err'); }
        });
    }

    function startPing() { clearInterval(pingTimer); if(mode!=='clipboard'){ping(); pingTimer=setInterval(ping,PING_INTERVAL);} }

    function applyHost(v) {
        host = v.replace(/\/+$/,''); GM_setValue(STORAGE_HOST, host);
        wsConn = false; renderHost(); showEditMode(false);
        if(enabled) startPing(); setStatus('Host cập nhật','ok');
    }

    function setMode(m) {
        mode = m; GM_setValue(STORAGE_MODE, m);
        clearInterval(pingTimer);
        if (ws) { try{ws.close();}catch(e){} ws=null; wsConn=false; }
        renderMode();
        if (m === 'clipboard') {
            setStatus('📋 Clipboard mode — không cần host','warn', 4000);
        } else {
            startPing();
        }
    }

    function toggleEnabled() {
        enabled = !enabled; GM_setValue(STORAGE_ON, enabled); renderToggle();
        if (enabled) { startPing(); setStatus('Đã bật','ok'); }
        else { clearInterval(pingTimer); if(ws)ws.close(); applyConnState('idle'); setStatus('Đã tắt','warn',3000); }
    }

    // ── TX Send ───────────────────────────────────────────────────────────────
    function highlightOrderId(row) {
        const match = row.innerText.match(/\d{3,}-\d+/); if(!match) return;
        const id = match[0];
        const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while(node = walker.nextNode()) {
            if(!node.nodeValue.includes(id)) continue;
            const frag = document.createDocumentFragment();
            node.nodeValue.split(id).forEach((part,i,a) => {
                frag.appendChild(document.createTextNode(part));
                if(i<a.length-1){const s=document.createElement('span');s.style.cssText='background:rgba(0,255,65,.25);border:1px solid #00cc44;padding:1px 3px;border-radius:2px;';s.textContent=id;frag.appendChild(s);}
            });
            node.parentNode.replaceChild(frag, node); break;
        }
    }

    function markSent(row, btn) {
        highlightOrderId(row);
        btn.innerText = '✓'; btn.style.background = '#00cc44'; btn.style.color = '#000';
        sentCount++; setStatus(`Đã gửi: ${sentCount} đơn`, 'ok', 0);
    }

    function markFail(btn, orig) {
        btn.innerText = orig.t; btn.style.background = orig.bg; btn.style.color = orig.c;
        setStatus('Lỗi gửi!','err'); applyConnState('err');
    }

    function sendData(row, btn) {
        if (!enabled) return setStatus('TX đang tắt!','warn');
        const orig = {t:btn.innerText, bg:btn.style.background, c:btn.style.color};
        btn.innerText = '…'; btn.style.background = '#ff9900'; btn.style.color = '#000';

        const imageUrl = findImageUrl(row);

        const payload = {
            source_url: location.href,
            title: document.title,
            html_fragments: [row.outerHTML],
            full_text: row.innerText,
            image_url: imageUrl
        };

        // ── Mode: Clipboard (hostless) ────────────────────────────────────────
        if (mode === 'clipboard') {
            try {
                const clipText = CLIP_MARKER + JSON.stringify(payload);
                GM_setClipboard(clipText, 'text');
                markSent(row, btn);
            } catch(e) {
                markFail(btn, orig);
            }
            return;
        }

        if (connState === 'err') return (btn.innerText=orig.t, btn.style.background=orig.bg, btn.style.color=orig.c, setStatus('Không có kết nối!','err'));

        // ── Mode: WebSocket ───────────────────────────────────────────────────
        if (mode === 'websocket' && ws && ws.readyState === WebSocket.OPEN) {
            try { ws.send(JSON.stringify(payload)); markSent(row, btn); } catch(e) { markFail(btn,orig); }
            return;
        }

        // ── Mode: HTTP (fallback) ─────────────────────────────────────────────
        GM_xmlhttpRequest({
            method:'POST', url: getUrl(RECEIVE_PATH),
            data: JSON.stringify(payload), headers:{'Content-Type':'application/json'}, timeout:5000,
            onload()  { markSent(row, btn); },
            onerror() { markFail(btn, orig); },
            ontimeout(){ btn.innerText=orig.t; btn.style.background=orig.bg; btn.style.color=orig.c; setStatus('Timeout!','err'); }
        });
    }

    // ── Process rows ──────────────────────────────────────────────────────────
    function processRows(rows) {
        rows.forEach(row => {
            if (row.getAttribute(PROCESSED_ATTR)) return;
            if (!/\d{3,}-\d+/.test(row.innerText)) return;
            if (!row.cells || row.cells.length < 2) return;
            const btn = document.createElement('button');
            btn.className = 'tx-btn'; btn.innerText = 'TX'; btn.title = 'Gửi đến TX App';
            btn.onclick = e => { e.stopPropagation(); e.preventDefault(); sendData(row, btn); };
            row.cells[1].insertBefore(btn, row.cells[1].firstChild);
            row.setAttribute(PROCESSED_ATTR, 'true');
        });
    }

    // ── Events ────────────────────────────────────────────────────────────────
    modeBtns.forEach(b => b.onclick = () => setMode(b.dataset.mode));
    btnToggle.onclick  = toggleEnabled;
    btnEdit.onclick    = () => showEditMode(true);
    btnSave.onclick    = () => { const v=hostInput.value.trim(); if(!v) return setStatus('Host rỗng!','err'); applyHost(v); };
    hostInput.onkeydown = e => { if(e.key==='Enter') btnSave.onclick(); if(e.key==='Escape') showEditMode(false); };
    btnReset.onclick   = () => { applyHost(DEFAULT_HOST); setStatus('Reset mặc định','ok'); };
    connRow.ondblclick = () => showEditMode(true);
    btnMin.onclick     = () => { panel.style.display='none'; minBtn.style.display='block'; };
    minBtn.onclick     = () => { panel.style.display='block'; minBtn.style.display='none'; };

    // Drag
    wrap.querySelector('#emb-hdr').addEventListener('mousedown', e => {
        if(e.target.tagName==='BUTTON') return;
        let ox=e.clientX, oy=e.clientY, r=wrap.getBoundingClientRect();
        let sr=window.innerWidth-r.right, sb=window.innerHeight-r.bottom;
        const mv = m => { wrap.style.right=Math.max(0,sr-(m.clientX-ox))+'px'; wrap.style.bottom=Math.max(0,sb+(m.clientY-oy))+'px'; };
        const up = () => { removeEventListener('mousemove',mv); removeEventListener('mouseup',up); };
        addEventListener('mousemove',mv); addEventListener('mouseup',up);
    });

    // ── Init ──────────────────────────────────────────────────────────────────
    renderHost(); renderToggle(); renderMode();
    if (enabled && mode !== 'clipboard') startPing();
    processRows(document.querySelectorAll('tr'));

    const observer = new MutationObserver(mutations => {
        const rows = [];
        mutations.forEach(({addedNodes}) => addedNodes.forEach(n => {
            if(n.nodeType!==1) return;
            n.tagName==='TR' ? rows.push(n) : n.querySelectorAll('tr').forEach(tr=>rows.push(tr));
        }));
        if(rows.length) processRows(rows);
    });
    observer.observe(document.body, {childList:true, subtree:true});

})();
