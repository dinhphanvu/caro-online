/* ==========================================================================
   CARO ONLINE - client
   Bàn cờ 15x15, thắng khi có 5 quân liền theo hàng / cột / đường chéo.
   ========================================================================== */

'use strict';

/* ------------------------- Cấu hình bàn cờ ------------------------------ */

const SIZE = 15;          // 15 giao điểm
const MARGIN = 20;        // lề trong SVG (viewBox 600x600)
const GAP = 40;           // khoảng cách giữa 2 giao điểm
const STONE_R = 16.5;     // bán kính quân cờ
const STAR_POINTS = [[3, 3], [11, 3], [3, 11], [11, 11], [7, 7]];

const SVG_NS = 'http://www.w3.org/2000/svg';

// sessionStorage là theo TỪNG TAB nên mở 2 tab không cướp ghế của nhau.
// localStorage chỉ dùng để ghi nhớ tên người chơi.
const SS_KEY = 'caro_online_session';
const LS_NAME = 'caro_online_name';

/* ------------------------------ Trạng thái ------------------------------ */

const S = {
  ws: null,
  connected: false,
  name: '',
  room: null,
  token: null,
  color: null,            // 'black' | 'white' - màu quân của tôi
  board: makeBoard(),
  turn: null,
  status: 'menu',         // menu | waiting | playing | over
  scores: { black: 0, white: 0 },
  players: [],
  winCells: [],
  lastMove: null,
  moves: 0,
  reconnectTries: 0,
  reconnectTimer: null,
  drawPending: false,     // tôi đã gửi lời mời hòa
  ghost: null,
};

function makeBoard() {
  return Array.from({ length: SIZE }, () => Array(SIZE).fill(null));
}

/* ------------------------------ DOM refs -------------------------------- */

const $ = (id) => document.getElementById(id);

const el = {
  screenMenu: $('screen-menu'),
  screenGame: $('screen-game'),
  inpName: $('inp-name'),
  inpCode: $('inp-code'),
  btnCreate: $('btn-create'),
  btnJoin: $('btn-join'),
  menuStatus: $('menu-status'),

  btnBack: $('btn-back'),
  btnRoomCode: $('btn-room-code'),
  turnBar: $('turn-bar'),
  turnDot: $('turn-dot'),
  turnText: $('turn-text'),

  nameBlack: $('name-black'),
  nameWhite: $('name-white'),
  scoreBlack: $('score-black'),
  scoreWhite: $('score-white'),
  scoreMid: $('score-mid'),

  board: $('board'),
  layerGrid: $('layer-grid'),
  layerStones: $('layer-stones'),
  layerMarks: $('layer-marks'),

  overlayWait: $('overlay-wait'),
  waitCode: $('wait-code'),
  btnCopyWait: $('btn-copy-wait'),
  btnShare: $('btn-share'),

  overlayResult: $('overlay-result'),
  resultEmoji: $('result-emoji'),
  resultTitle: $('result-title'),
  resultSub: $('result-sub'),
  btnRematch: $('btn-rematch'),
  btnResultLeave: $('btn-result-leave'),

  btnOfferDraw: $('btn-offer-draw'),
  btnRematchLive: $('btn-rematch-live'),
  btnResign: $('btn-resign'),

  chatPanel: $('chat-panel'),
  chatList: $('chat-list'),
  chatForm: $('chat-form'),
  chatInput: $('chat-input'),
  btnChatToggle: $('btn-chat-toggle'),

  modalDraw: $('modal-draw'),
  btnDrawYes: $('btn-draw-yes'),
  btnDrawNo: $('btn-draw-no'),

  toast: $('toast'),
};

/* ------------------------------ Vẽ bàn cờ ------------------------------- */

function cellXY(c, r) {
  return [MARGIN + c * GAP, MARGIN + r * GAP];
}

function buildBoard() {
  const grid = el.layerGrid;
  grid.textContent = '';

  // các đường kẻ: 15 hàng + 15 cột
  for (let i = 0; i < SIZE; i++) {
    const p = MARGIN + i * GAP;
    const isEdge = i === 0 || i === SIZE - 1;

    const h = document.createElementNS(SVG_NS, 'line');
    h.setAttribute('x1', MARGIN);
    h.setAttribute('y1', p);
    h.setAttribute('x2', MARGIN + (SIZE - 1) * GAP);
    h.setAttribute('y2', p);
    if (isEdge) h.setAttribute('class', 'edge');
    grid.appendChild(h);

    const v = document.createElementNS(SVG_NS, 'line');
    v.setAttribute('x1', p);
    v.setAttribute('y1', MARGIN);
    v.setAttribute('x2', p);
    v.setAttribute('y2', MARGIN + (SIZE - 1) * GAP);
    if (isEdge) v.setAttribute('class', 'edge');
    grid.appendChild(v);
  }

  // các điểm sao
  for (const [c, r] of STAR_POINTS) {
    const [x, y] = cellXY(c, r);
    const dot = document.createElementNS(SVG_NS, 'circle');
    dot.setAttribute('cx', x);
    dot.setAttribute('cy', y);
    dot.setAttribute('r', 4);
    dot.setAttribute('class', 'hoshi');
    grid.appendChild(dot);
  }
}

/** Tạo 1 quân cờ SVG. */
function makeStone(color) {
  const g = document.createElementNS(SVG_NS, 'g');
  g.setAttribute('class', 'stone-g');

  const shadow = document.createElementNS(SVG_NS, 'circle');
  shadow.setAttribute('r', STONE_R + 1.5);
  shadow.setAttribute('fill', 'url(#gradShadow)');
  shadow.setAttribute('cx', 1.5);
  shadow.setAttribute('cy', 2);
  g.appendChild(shadow);

  const body = document.createElementNS(SVG_NS, 'circle');
  body.setAttribute('r', STONE_R);
  body.setAttribute('class', 'body');
  body.setAttribute('fill', color === 'black' ? 'url(#gradBlack)' : 'url(#gradWhite)');
  g.appendChild(body);

  return g;
}

/** Vẽ lại toàn bộ các quân cờ + đánh dấu. */
function renderStones() {
  el.layerStones.textContent = '';
  el.layerMarks.textContent = '';

  for (let r = 0; r < SIZE; r++) {
    for (let c = 0; c < SIZE; c++) {
      const color = S.board[r][c];
      if (!color) continue;
      const [x, y] = cellXY(c, r);
      const g = makeStone(color);
      g.setAttribute('transform', `translate(${x},${y})`);
      g.dataset.c = c;
      g.dataset.r = r;
      el.layerStones.appendChild(g);
    }
  }

  // chấm đỏ đánh dấu nước đi cuối
  if (S.lastMove) {
    const [c, r] = S.lastMove;
    const [x, y] = cellXY(c, r);
    const dot = document.createElementNS(SVG_NS, 'circle');
    dot.setAttribute('cx', x);
    dot.setAttribute('cy', y);
    dot.setAttribute('r', 3.4);
    dot.setAttribute('class', 'last-marker');
    el.layerMarks.appendChild(dot);
  }

  // highlight đường thắng
  if (S.winCells && S.winCells.length >= 2) {
    const pts = S.winCells.map(([c, r]) => cellXY(c, r));
    for (const [x, y] of pts) {
      const glow = document.createElementNS(SVG_NS, 'circle');
      glow.setAttribute('cx', x);
      glow.setAttribute('cy', y);
      glow.setAttribute('r', STONE_R + 4);
      glow.setAttribute('class', 'win-glow');
      el.layerMarks.appendChild(glow);
    }
    const [x1, y1] = pts[0];
    const [x2, y2] = pts[pts.length - 1];
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('class', 'win-line');
    el.layerMarks.appendChild(line);
  }
}

/* --------------------------- Xác định ô cờ ------------------------------ */

function pickCell(clientX, clientY) {
  const rect = el.board.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const sx = (clientX - rect.left) * (600 / rect.width);
  const sy = (clientY - rect.top) * (600 / rect.height);
  const c = Math.round((sx - MARGIN) / GAP);
  const r = Math.round((sy - MARGIN) / GAP);
  if (c < 0 || c >= SIZE || r < 0 || r >= SIZE) return null;
  const [px, py] = cellXY(c, r);
  // phải bấm đủ gần giao điểm
  if (Math.hypot(sx - px, sy - py) > GAP * 0.62) return null;
  return [c, r];
}

function showGhost(c, r) {
  clearGhost();
  if (S.board[r][c] !== null) return;
  const [x, y] = cellXY(c, r);
  const g = document.createElementNS(SVG_NS, 'circle');
  g.setAttribute('cx', x);
  g.setAttribute('cy', y);
  g.setAttribute('r', STONE_R);
  g.setAttribute('class', 'hover-marker');
  el.layerMarks.appendChild(g);
  S.ghost = g;
}

function clearGhost() {
  if (S.ghost && S.ghost.parentNode) S.ghost.parentNode.removeChild(S.ghost);
  S.ghost = null;
}

let pressCell = null;

function canPlay() {
  return S.status === 'playing' && S.turn === S.color && S.connected;
}

function onPointerDown(e) {
  if (!canPlay()) return;
  const cell = pickCell(e.clientX, e.clientY);
  if (!cell) return;
  const [c, r] = cell;
  if (S.board[r][c] !== null) return;
  pressCell = cell;
  showGhost(c, r);
}

function onPointerUp(e) {
  if (!pressCell) return;
  const cell = pickCell(e.clientX, e.clientY);
  const same = cell && cell[0] === pressCell[0] && cell[1] === pressCell[1];
  pressCell = null;
  clearGhost();
  if (same) send({ type: 'move', x: cell[0], y: cell[1] });
}

function onPointerCancel() {
  pressCell = null;
  clearGhost();
}

/* ------------------------------ Kết nối --------------------------------- */

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  return proto + location.host + '/ws';
}

function connect() {
  clearTimeout(S.reconnectTimer);
  let ws;
  try {
    ws = new WebSocket(wsUrl());
  } catch (err) {
    scheduleReconnect();
    return;
  }
  S.ws = ws;

  ws.onopen = () => {
    S.connected = true;
    S.reconnectTries = 0;
    updateTurnBar();

    // nếu có phiên cũ trong tab này thì thử vào lại phòng
    const saved = loadSession();
    if (saved && saved.room && saved.token) {
      send({
        type: 'join',
        room: saved.room,
        token: saved.token,
        name: S.name,
      });
    } else if (S.room && S.token) {
      send({ type: 'join', room: S.room, token: S.token, name: S.name });
    }
  };

  ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (err) {
      return;
    }
    handleMessage(msg);
  };

  ws.onclose = () => {
    S.connected = false;
    updateTurnBar();
    if (S.status !== 'menu') {
      toast('Mất kết nối, đang thử nối lại…');
      scheduleReconnect();
    }
  };

  ws.onerror = () => {
    try {
      ws.close();
    } catch (err) { /* bỏ qua */ }
  };
}

function scheduleReconnect() {
  if (S.status === 'menu') return;
  S.reconnectTries += 1;
  const delay = Math.min(1000 * Math.pow(1.6, S.reconnectTries - 1), 10000);
  clearTimeout(S.reconnectTimer);
  S.reconnectTimer = setTimeout(connect, delay);
}

function send(payload) {
  if (S.ws && S.ws.readyState === WebSocket.OPEN) {
    S.ws.send(JSON.stringify(payload));
    return true;
  }
  toast('Đang mất kết nối, chưa gửi được.');
  return false;
}

/* ------------------------- Xử lý tin nhắn server ------------------------ */

function handleMessage(msg) {
  switch (msg.type) {
    case 'created':
      S.room = msg.room;
      S.token = msg.token;
      S.color = msg.color;
      applyState(msg.state);
      saveSession();
      showGame();
      break;

    case 'start':
    case 'reconnected':
      S.room = msg.room;
      S.token = msg.token || S.token;
      S.color = msg.color;
      applyState(msg.state);
      saveSession();
      showGame();
      if (msg.type === 'reconnected') toast('Đã kết nối lại ván đấu.');
      break;

    case 'waiting':
      S.room = msg.room;
      S.status = 'waiting';
      updateUI();
      break;

    case 'move':
      if (typeof msg.x === 'number') {
        S.board[msg.y][msg.x] = msg.color;
        S.lastMove = [msg.x, msg.y];
      }
      if (msg.state) applyState(msg.state);
      if (msg.result) showResult(msg.result);
      renderStones();
      updateUI();
      break;

    case 'restart':
      applyState(msg.state);
      hideResult();
      renderStones();
      updateUI();
      addChatSystem(msg.first === S.color
        ? 'Ván mới bắt đầu — bạn đi trước.'
        : 'Ván mới bắt đầu — đối phương đi trước.');
      toast('Ván mới bắt đầu!');
      break;

    case 'resign':
      applyState(msg.state);
      showResult({ winner: msg.winner });
      updateUI();
      break;

    case 'forfeit':
      applyState(msg.state);
      showResult({ winner: msg.winner, reason: msg.reason });
      updateUI();
      break;

    case 'draw':
      applyState(msg.state);
      showResult({ winner: 'draw' });
      updateUI();
      break;

    case 'draw_offer':
      S.drawPending = false;
      el.modalDraw.classList.remove('hidden');
      break;

    case 'draw_declined':
      S.drawPending = false;
      toast('Đối phương từ chối hòa.');
      updateUI();
      break;

    case 'chat':
      addChatMsg(msg.name, msg.color, msg.text, msg.color === S.color);
      break;

    case 'opp_disconnected':
      toast(`Đối phương mất kết nối. Chờ ${msg.grace} giây…`);
      break;

    case 'opp_reconnected':
      toast('Đối phương đã kết nối lại.');
      break;

    case 'opp_left':
      toast('Đối phương đã rời phòng.');
      break;

    case 'error':
      toast(msg.msg || 'Có lỗi xảy ra.');
      if (/Không tìm thấy phòng/.test(msg.msg || '')) {
        clearSession();
        S.room = null;
        S.token = null;
        S.color = null;
        S.status = 'menu';
        showMenu();
      }
      break;
  }
}

function applyState(state) {
  if (!state) return;
  if (state.board) S.board = state.board;
  S.turn = state.turn ?? null;
  S.status = state.status || S.status;
  S.scores = state.scores || S.scores;
  S.winCells = state.winCells || [];
  S.lastMove = state.lastMove || null;
  S.moves = state.moves || 0;
  S.players = state.players || [];

  if (S.status === 'playing' && S.winCells.length === 0) hideResult();
}

/* ------------------------------ Hiển thị -------------------------------- */

function showMenu() {
  el.screenMenu.classList.add('active');
  el.screenGame.classList.remove('active');
  el.overlayResult.classList.add('hidden');
  el.overlayWait.classList.add('hidden');
}

function showGame() {
  el.screenMenu.classList.remove('active');
  el.screenGame.classList.add('active');
  renderStones();
  updateUI();
}

function colorName(color) {
  return color === 'black' ? 'Đen' : 'Trắng';
}

function myName() {
  return S.name || 'Bạn';
}

function updateUI() {
  const isWaiting = S.status === 'waiting';
  const isPlaying = S.status === 'playing';
  const isOver = S.status === 'over';

  // mã phòng
  const code = S.room || '----';
  el.btnRoomCode.textContent = code;
  el.waitCode.textContent = code;

  // overlay chờ
  el.overlayWait.classList.toggle('hidden', !(isWaiting && S.color === 'black'));

  // bảng điểm
  const black = S.players.find((p) => p.color === 'black');
  const white = S.players.find((p) => p.color === 'white');
  el.nameBlack.textContent = black ? black.name : 'Đen';
  el.nameWhite.textContent = white ? white.name : 'Trắng';
  el.scoreBlack.textContent = S.scores.black ?? 0;
  el.scoreWhite.textContent = S.scores.white ?? 0;
  el.scoreMid.textContent = `${S.scores.black ?? 0} : ${S.scores.white ?? 0}`;

  // thanh lượt đi
  updateTurnBar();

  // nút hành động
  el.btnResign.disabled = !isPlaying || !S.connected;
  el.btnOfferDraw.disabled = !isPlaying || S.drawPending || !S.connected;
  el.btnRematchLive.disabled = !isOver;
  el.btnOfferDraw.textContent = '';
  el.btnOfferDraw.append('🤝');
  const spanD = document.createElement('span');
  spanD.textContent = S.drawPending ? 'Đã mời' : 'Hòa';
  el.btnOfferDraw.appendChild(spanD);
}

function updateTurnBar() {
  const dot = el.turnDot;
  const text = el.turnText;
  dot.className = 'turn-dot';
  el.turnBar.classList.remove('my-turn');

  if (!S.connected) {
    text.textContent = 'Đang mất kết nối…';
    return;
  }
  if (S.status === 'waiting') {
    text.textContent = S.color === 'black'
      ? 'Chờ bạn mời người thứ hai…'
      : 'Đang chờ đối phương…';
    return;
  }
  if (S.status === 'over') {
    text.textContent = 'Ván đấu đã kết thúc';
    return;
  }
  if (!S.turn) return;

  dot.classList.add(S.turn);
  if (S.turn === S.color) {
    el.turnBar.classList.add('my-turn');
    text.textContent = `Đến lượt bạn (${colorName(S.color)})`;
  } else {
    text.textContent = 'Đến lượt đối phương';
  }
}

/* ------------------------------ Kết quả --------------------------------- */

function showResult(result) {
  S.status = 'over';
  const winner = result.winner;
  const reason = result.reason ? ` ${result.reason}` : '';

  if (winner === 'draw') {
    el.resultEmoji.textContent = '🤝';
    el.resultTitle.textContent = 'Hòa!';
    el.resultSub.textContent = `Cả hai bất phân thắng bại sau ${S.moves} nước.${reason}`;
  } else if (winner === S.color) {
    el.resultEmoji.textContent = '🏆';
    el.resultTitle.textContent = 'Bạn thắng!';
    el.resultSub.textContent = `Chiến thắng đẹp sau ${S.moves} nước.${reason}`;
    beep(880, 0.12);
    setTimeout(() => beep(1320, 0.18), 130);
  } else {
    el.resultEmoji.textContent = '😔';
    el.resultTitle.textContent = 'Bạn thua rồi';
    el.resultSub.textContent = `Đối phương tạo được 5 quân liền.${reason}`;
    beep(320, 0.2);
  }

  el.overlayResult.classList.remove('hidden');
  updateUI();
}

function hideResult() {
  el.overlayResult.classList.add('hidden');
}

/* ------------------------------- Chat ----------------------------------- */

function addChatMsg(name, color, text, mine) {
  const div = document.createElement('div');
  div.className = 'chat-msg' + (mine ? ' mine' : '');
  const b = document.createElement('b');
  b.textContent = (mine ? 'Bạn' : name) + (color ? ` (${colorName(color)})` : '');
  div.appendChild(b);
  div.appendChild(document.createTextNode(text));
  el.chatList.appendChild(div);
  el.chatList.scrollTop = el.chatList.scrollHeight;
}

function addChatSystem(text) {
  const div = document.createElement('div');
  div.className = 'chat-sys';
  div.textContent = text;
  el.chatList.appendChild(div);
  el.chatList.scrollTop = el.chatList.scrollHeight;
}

/* ------------------------------ Tiện ích -------------------------------- */

let toastTimer = null;
function toast(text) {
  el.toast.textContent = text;
  el.toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.add('hidden'), 2600);
}

let audioCtx = null;
function beep(freq, dur) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = freq;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.001, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.25, audioCtx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + dur + 0.02);
  } catch (err) { /* bỏ qua */ }
}

function saveSession() {
  try {
    sessionStorage.setItem(SS_KEY, JSON.stringify({
      room: S.room,
      token: S.token,
      color: S.color,
    }));
    saveName(S.name);
  } catch (err) { /* bỏ qua */ }
}

function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SS_KEY) || 'null');
  } catch (err) {
    return null;
  }
}

function clearSession() {
  try {
    sessionStorage.removeItem(SS_KEY);
  } catch (err) { /* bỏ qua */ }
}

function saveName(name) {
  try {
    if (name) localStorage.setItem(LS_NAME, name);
  } catch (err) { /* bỏ qua */ }
}

function loadName() {
  try {
    return localStorage.getItem(LS_NAME) || '';
  } catch (err) {
    return '';
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Đã sao chép: ' + text);
  } catch (err) {
    // fallback cho iOS Safari cũ
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      toast('Đã sao chép: ' + text);
    } catch (e2) {
      toast('Không sao chép được, hãy ghi nhớ mã: ' + text);
    }
    document.body.removeChild(ta);
  }
}

function leaveRoom() {
  send({ type: 'leave' });
  clearSession();
  S.room = null;
  S.token = null;
  S.color = null;
  S.status = 'menu';
  S.board = makeBoard();
  S.turn = null;
  S.lastMove = null;
  S.winCells = [];
  S.moves = 0;
  S.scores = { black: 0, white: 0 };
  S.players = [];
  S.drawPending = false;
  el.chatList.textContent = '';
  el.chatPanel.classList.remove('open');
  hideResult();
  showMenu();
}

/* ------------------------------ Sự kiện --------------------------------- */

function boot() {
  buildBoard();

  // khôi phục tên đã lưu
  el.inpName.value = loadName();

  el.btnCreate.addEventListener('click', () => {
    const name = el.inpName.value.trim();
    if (!name) {
      el.menuStatus.textContent = 'Hãy nhập tên của bạn trước.';
      el.inpName.focus();
      return;
    }
    el.menuStatus.textContent = '';
    S.name = name;
    el.btnCreate.disabled = true;
    if (S.connected) send({ type: 'create', name });
    else {
      connect();
      setTimeout(() => {
        send({ type: 'create', name });
        el.btnCreate.disabled = false;
      }, 700);
    }
    setTimeout(() => { el.btnCreate.disabled = false; }, 2500);
  });

  el.btnJoin.addEventListener('click', () => {
    const name = el.inpName.value.trim();
    const code = el.inpCode.value.trim().toUpperCase();
    if (!name) {
      el.menuStatus.textContent = 'Hãy nhập tên của bạn trước.';
      el.inpName.focus();
      return;
    }
    if (code.length !== 4) {
      el.menuStatus.textContent = 'Mã phòng gồm 4 ký tự.';
      el.inpCode.focus();
      return;
    }
    el.menuStatus.textContent = '';
    S.name = name;
    clearSession();
    if (S.connected) send({ type: 'join', room: code, name });
    else {
      connect();
      setTimeout(() => send({ type: 'join', room: code, name }), 700);
    }
  });

  el.inpCode.addEventListener('input', () => {
    el.inpCode.value = el.inpCode.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 4);
  });
  el.inpCode.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el.btnJoin.click();
  });
  el.inpName.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el.btnCreate.click();
  });

  // bàn cờ
  el.board.addEventListener('pointerdown', onPointerDown);
  el.board.addEventListener('pointerup', onPointerUp);
  el.board.addEventListener('pointercancel', onPointerCancel);
  el.board.addEventListener('pointerleave', onPointerCancel);
  el.board.addEventListener('contextmenu', (e) => e.preventDefault());

  // mã phòng -> sao chép
  el.btnRoomCode.addEventListener('click', () => S.room && copyText(S.room));
  el.btnCopyWait.addEventListener('click', () => S.room && copyText(S.room));
  el.btnShare.addEventListener('click', async () => {
    const text = `Vào chơi Caro với mình! Mã phòng: ${S.room}`;
    const url = location.origin + '/?room=' + S.room;
    if (navigator.share) {
      try {
        await navigator.share({ title: 'Caro Online', text, url });
        return;
      } catch (err) { /* người dùng hủy */ }
    }
    copyText(url);
  });

  // nút hành động
  el.btnResign.addEventListener('click', () => {
    if (!confirm('Bạn chắc chắn muốn bỏ cuộc?')) return;
    send({ type: 'resign' });
  });

  el.btnOfferDraw.addEventListener('click', () => {
    if (send({ type: 'draw_offer' })) {
      S.drawPending = true;
      toast('Đã gửi lời mời hòa.');
      updateUI();
    }
  });

  const requestRematch = () => {
    if (send({ type: 'restart' })) toast('Đã gửi lời mời đấu lại.');
  };
  el.btnRematchLive.addEventListener('click', requestRematch);
  el.btnRematch.addEventListener('click', requestRematch);

  el.btnDrawYes.addEventListener('click', () => {
    el.modalDraw.classList.add('hidden');
    send({ type: 'draw_response', accepted: true });
  });
  el.btnDrawNo.addEventListener('click', () => {
    el.modalDraw.classList.add('hidden');
    send({ type: 'draw_response', accepted: false });
  });

  el.btnBack.addEventListener('click', () => {
    if (!confirm('Rời phòng? Ván đấu hiện tại sẽ kết thúc.')) return;
    leaveRoom();
  });
  el.btnResultLeave.addEventListener('click', leaveRoom);

  // chat
  el.btnChatToggle.addEventListener('click', () => {
    el.chatPanel.classList.toggle('open');
    if (el.chatPanel.classList.contains('open')) el.chatInput.focus();
  });
  el.chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = el.chatInput.value.trim();
    if (!text) return;
    if (send({ type: 'chat', text })) {
      addChatMsg(S.name, S.color, text, true);
      el.chatInput.value = '';
    }
  });

  // vào thẳng phòng nếu có link ?room=XXXX
  const params = new URLSearchParams(location.search);
  const roomParam = (params.get('room') || '').toUpperCase();
  if (/^[A-Z0-9]{4}$/.test(roomParam)) {
    el.inpCode.value = roomParam;
    el.inpName.focus();
  }

  connect();

  // PWA
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* bỏ qua */ });
  }
}

document.addEventListener('DOMContentLoaded', boot);
