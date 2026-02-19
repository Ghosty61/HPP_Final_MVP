/* ── Auth helpers ────────────────────────────────────────────── */

function getToken() {
  return localStorage.getItem('hpp_token');
}

function saveSession(token, user) {
  localStorage.setItem('hpp_token', token);
  localStorage.setItem('hpp_user', JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem('hpp_token');
  localStorage.removeItem('hpp_user');
}

function showAlert(elId, message, type) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = message;
  el.className = 'alert ' + type;
}

function setButtonLoading(btn, loading) {
  btn.disabled = loading;
  btn.innerHTML = loading
    ? '<span class="spinner"></span>Please wait…'
    : btn.dataset.label;
}

/* ── View switching ──────────────────────────────────────────── */

function showApp(user) {
  document.getElementById('authSection').style.display = 'none';
  document.getElementById('calcSection').style.display  = 'block';
  document.getElementById('userInfo').style.display     = 'flex';
  document.getElementById('userName').textContent       = user.name;
}

function showAuth() {
  document.getElementById('authSection').style.display = 'block';
  document.getElementById('calcSection').style.display  = 'none';
  document.getElementById('userInfo').style.display     = 'none';
}

/* ── Tab switching ───────────────────────────────────────────── */

function switchTab(tab) {
  document.getElementById('tabLogin').classList.toggle('active',    tab === 'login');
  document.getElementById('tabRegister').classList.toggle('active', tab === 'register');
  document.getElementById('loginForm').classList.toggle('active',    tab === 'login');
  document.getElementById('registerForm').classList.toggle('active', tab === 'register');
  document.getElementById('loginAlert').className    = 'alert';
  document.getElementById('registerAlert').className = 'alert';
}

/* ── API calls ───────────────────────────────────────────────── */

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}

/* ── Login handler ───────────────────────────────────────────── */

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('loginBtn');
  btn.dataset.label = btn.textContent;

  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;

  setButtonLoading(btn, true);
  try {
    const { token, user } = await apiPost('/api/login', { email, password });
    saveSession(token, user);
    showApp(user);
  } catch (err) {
    showAlert('loginAlert', err.message, 'error');
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ── Register handler ────────────────────────────────────────── */

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('registerBtn');
  btn.dataset.label = btn.textContent;

  const name     = document.getElementById('regName').value.trim();
  const email    = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;

  setButtonLoading(btn, true);
  try {
    const { token, user } = await apiPost('/api/register', { name, email, password });
    saveSession(token, user);
    showApp(user);
  } catch (err) {
    showAlert('registerAlert', err.message, 'error');
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ── Logout handler ──────────────────────────────────────────── */

document.getElementById('logoutBtn').addEventListener('click', () => {
  clearSession();
  showAuth();
  document.getElementById('loginEmail').value    = '';
  document.getElementById('loginPassword').value = '';
  switchTab('login');
});

/* ── Session check on load ───────────────────────────────────── */

(async function init() {
  const token = getToken();
  if (!token) return showAuth();

  try {
    const res = await fetch('/api/me', {
      headers: { Authorization: 'Bearer ' + token },
    });
    if (!res.ok) throw new Error('session expired');
    const { user } = await res.json();
    showApp(user);
  } catch {
    clearSession();
    showAuth();
  }
})();
