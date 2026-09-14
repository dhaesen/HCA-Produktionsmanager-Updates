'use strict';

/* HCA v0.13.5: Benutzeranmeldung, Benutzerverwaltung und persönliche E-Mail-Signaturen. */
(() => {
  const $a = selector => document.querySelector(selector);
  const escA = value => escapeHtml(String(value == null ? '' : value));
  let currentUser = null;
  let users = [];
  let signatureEditor = null;

  function cleanHtml(source) {
    const template = document.createElement('template');
    template.innerHTML = String(source || '');
    const allowed = new Set(['B','STRONG','I','EM','U','S','P','DIV','BR','UL','OL','LI','A','H1','H2','H3','BLOCKQUOTE','SPAN']);
    const visit = node => {
      [...node.children].forEach(child => {
        if (!allowed.has(child.tagName)) {
          const children = [...child.childNodes];
          child.replaceWith(...children);
          children.filter(x => x.nodeType === 1).forEach(visit);
          return;
        }
        [...child.attributes].forEach(attribute => {
          const name = attribute.name.toLowerCase();
          if (child.tagName === 'A' && name === 'href') {
            if (!/^(https?:|mailto:)/i.test(String(attribute.value || '').trim())) child.removeAttribute(attribute.name);
          } else if (child.tagName === 'A' && name === 'target') {
            child.setAttribute('target', '_blank');
            child.setAttribute('rel', 'noopener');
          } else if (name === 'style') {
            const safe = String(attribute.value || '').split(';')
              .filter(rule => /^\s*(text-align|color|background-color|font-size)\s*:/i.test(rule))
              .join(';');
            safe ? child.setAttribute('style', safe) : child.removeAttribute('style');
          } else {
            child.removeAttribute(attribute.name);
          }
        });
        visit(child);
      });
    };
    visit(template.content);
    return template.innerHTML;
  }

  async function authApi(path, options = {}) {
    return businessApi('/auth/' + path.replace(/^\//, ''), {
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})},
      timeoutMs: options.timeoutMs || 30000
    });
  }

  function loginShell(mode, message = '') {
    let overlay = $a('#hcaLoginOverlay');
    if (!overlay) {
      document.body.insertAdjacentHTML('beforeend', `
        <div id="hcaLoginOverlay" class="hca-login-overlay">
          <div class="hca-login-card">
            <img src="/assets/logo-app.png" alt="Werbestudio Königswinter">
            <div class="eyebrow">HCA PRODUKTIONSMANAGER</div>
            <h1 id="hcaLoginTitle">Anmelden</h1>
            <p id="hcaLoginIntro"></p>
            <form id="hcaLoginForm" autocomplete="on">
              <label id="hcaLoginNameWrap" class="hidden">Vollständiger Name
                <input id="hcaLoginName" class="text-input" autocomplete="name">
              </label>
              <label>Benutzername
                <input id="hcaLoginUsername" class="text-input" autocomplete="username" required>
              </label>
              <label>Passwort
                <input id="hcaLoginPassword" class="text-input" type="password" autocomplete="current-password" required>
              </label>
              <label id="hcaLoginConfirmWrap" class="hidden">Passwort wiederholen
                <input id="hcaLoginConfirm" class="text-input" type="password" autocomplete="new-password">
              </label>
              <label id="hcaRememberWrap" class="check-line"><input id="hcaLoginRemember" type="checkbox"> Auf diesem Arbeitsplatz angemeldet bleiben</label>
              <div id="hcaLoginError" class="hca-login-error"></div>
              <button id="hcaLoginSubmit" class="btn primary" type="submit">Anmelden</button>
            </form>
          </div>
        </div>`);
      overlay = $a('#hcaLoginOverlay');
    }
    overlay.classList.remove('hidden');
    overlay.dataset.mode = mode;
    const setup = mode === 'bootstrap';
    $a('#hcaLoginTitle').textContent = setup ? 'Ersten Administrator anlegen' : 'Bei HCA anmelden';
    $a('#hcaLoginIntro').textContent = setup
      ? 'Beim ersten Start wird ein Administratorkonto eingerichtet. Danach ist für HCA eine Anmeldung erforderlich.'
      : 'Bitte mit deinem persönlichen HCA-Konto anmelden.';
    $a('#hcaLoginNameWrap').classList.toggle('hidden', !setup);
    $a('#hcaLoginConfirmWrap').classList.toggle('hidden', !setup);
    $a('#hcaRememberWrap').classList.toggle('hidden', setup);
    $a('#hcaLoginPassword').autocomplete = setup ? 'new-password' : 'current-password';
    $a('#hcaLoginSubmit').textContent = setup ? 'Administratorkonto anlegen' : 'Anmelden';
    $a('#hcaLoginError').textContent = message;
    const form = $a('#hcaLoginForm');
    form.onsubmit = async event => {
      event.preventDefault();
      const username = $a('#hcaLoginUsername').value.trim();
      const password = $a('#hcaLoginPassword').value;
      const button = $a('#hcaLoginSubmit');
      if (setup && password !== $a('#hcaLoginConfirm').value) {
        $a('#hcaLoginError').textContent = 'Die beiden Passwörter stimmen nicht überein.';
        return;
      }
      button.disabled = true;
      $a('#hcaLoginError').textContent = '';
      try {
        const result = await authApi(setup ? 'bootstrap' : 'login', {
          method:'POST',
          body:JSON.stringify(setup
            ? {username, password, display_name:$a('#hcaLoginName').value.trim()}
            : {username, password, remember:!!$a('#hcaLoginRemember').checked})
        });
        window.hcaAuthSession.set(result.session_token);
        location.reload();
      } catch (error) {
        $a('#hcaLoginError').textContent = error.message || String(error);
      } finally {
        button.disabled = false;
      }
    };
    window.setTimeout(() => (setup ? $a('#hcaLoginName') : $a('#hcaLoginUsername'))?.focus(), 30);
  }

  function addUserChip() {
    const header = $a('.topbar');
    if (!header || $a('#hcaUserChip')) return;
    const chip = document.createElement('div');
    chip.id = 'hcaUserChip';
    chip.className = 'hca-user-chip';
    chip.innerHTML = `<div><b>${escA(currentUser.display_name || currentUser.username)}</b><span>${currentUser.role === 'admin' ? 'Administrator' : 'Mitarbeiter'}</span></div><button type="button" title="Abmelden">Abmelden</button>`;
    chip.querySelector('button').onclick = async () => {
      try { await authApi('logout', {method:'POST', body:'{}'}); } catch (_) {}
      window.hcaAuthSession.set('');
      location.reload();
    };
    header.appendChild(chip);
  }

  function signatureToolbar(target) {
    const command = (name, value = null) => {
      target.focus();
      document.execCommand(name, false, value);
    };
    const toolbar = document.createElement('div');
    toolbar.className = 'hca-rich-toolbar';
    toolbar.innerHTML = '<button type="button" data-cmd="bold"><b>B</b></button><button type="button" data-cmd="italic"><i>I</i></button><button type="button" data-cmd="underline"><u>U</u></button><span></span><button type="button" data-block="p">Text</button><button type="button" data-block="h3">Überschrift</button><button type="button" data-cmd="insertUnorderedList">• Liste</button><button type="button" data-link>Link</button><button type="button" data-cmd="removeFormat">Format löschen</button>';
    toolbar.querySelectorAll('[data-cmd]').forEach(button => button.onclick = () => command(button.dataset.cmd));
    toolbar.querySelectorAll('[data-block]').forEach(button => button.onclick = () => command('formatBlock', button.dataset.block));
    toolbar.querySelector('[data-link]').onclick = async () => {
      const link = await hcaPrompt('Vollständige Internetadresse eingeben:', 'https://');
      if (link && /^(https?:|mailto:)/i.test(link)) command('createLink', link);
    };
    return toolbar;
  }

  function mountUserSettings() {
    const grid = $a('#view-settings .settings-grid');
    if (!grid || $a('#hcaProfileSettings')) return;
    const profile = document.createElement('div');
    profile.id = 'hcaProfileSettings';
    profile.className = 'panel';
    profile.innerHTML = `
      <h2>Mein Benutzerprofil</h2>
      <p>Diese Signatur wird automatisch in jede neue E-Mail eingefügt.</p>
      <label>Anzeigename</label>
      <input id="hcaProfileDisplayName" class="text-input" value="${escA(currentUser.display_name || '')}">
      <label>Persönliche E-Mail-Signatur</label>
      <div id="hcaSignatureToolbarHost"></div>
      <div id="hcaSignatureEditor" class="hca-rich-content hca-signature-editor" contenteditable="true" role="textbox" aria-multiline="true"></div>
      <label>Eigenes Passwort ändern <span class="settings-note">(leer lassen, wenn es unverändert bleiben soll)</span></label>
      <input id="hcaProfilePassword" class="text-input" type="password" autocomplete="new-password" placeholder="Neues Passwort">
      <div class="actions-row"><button id="hcaSaveProfile" class="btn primary" type="button">Benutzerprofil speichern</button></div>`;
    grid.prepend(profile);
    signatureEditor = $a('#hcaSignatureEditor');
    signatureEditor.innerHTML = cleanHtml(currentUser.signature_html || '');
    $a('#hcaSignatureToolbarHost').appendChild(signatureToolbar(signatureEditor));
    $a('#hcaSaveProfile').onclick = saveProfile;

    if (currentUser.role === 'admin') mountUserAdministration(grid);
  }

  async function saveProfile() {
    const button = $a('#hcaSaveProfile');
    button.disabled = true;
    try {
      const result = await authApi('profile', {
        method:'PUT',
        body:JSON.stringify({
          display_name:$a('#hcaProfileDisplayName').value.trim(),
          signature_html:cleanHtml(signatureEditor.innerHTML),
          new_password:$a('#hcaProfilePassword').value
        })
      });
      currentUser = result.user;
      $a('#hcaProfilePassword').value = '';
      $a('#hcaUserChip b').textContent = currentUser.display_name || currentUser.username;
      alert('Benutzerprofil und E-Mail-Signatur wurden gespeichert.');
    } catch (error) {
      alert('Benutzerprofil konnte nicht gespeichert werden:\n' + (error.message || error));
    } finally {
      button.disabled = false;
    }
  }

  function mountUserAdministration(grid) {
    const panel = document.createElement('div');
    panel.id = 'hcaUserAdministration';
    panel.className = 'panel span-2';
    panel.innerHTML = `
      <h2>HCA-Benutzerverwaltung</h2>
      <p>Benutzer erhalten ein eigenes HCA-Passwort. Windows Hello und NFC werden später als zusätzliche Anmeldearten an diese Konten gebunden.</p>
      <div class="hca-user-create-grid">
        <input id="hcaNewUserName" class="text-input" placeholder="Vollständiger Name">
        <input id="hcaNewUsername" class="text-input" placeholder="Benutzername" autocomplete="off">
        <input id="hcaNewUserPassword" class="text-input" type="password" placeholder="Startpasswort" autocomplete="new-password">
        <select id="hcaNewUserRole" class="text-input"><option value="employee">Mitarbeiter</option><option value="admin">Administrator</option></select>
        <button id="hcaCreateUser" class="btn primary" type="button">Benutzer anlegen</button>
      </div>
      <div id="hcaUserList" class="business-card-list"></div>`;
    grid.prepend(panel);
    $a('#hcaCreateUser').onclick = createUser;
    loadUsers();
  }

  async function loadUsers() {
    try {
      const result = await authApi('users');
      users = result.items || [];
      renderUsers();
    } catch (error) {
      $a('#hcaUserList').innerHTML = '<div class="business-empty error">' + escA(error.message || error) + '</div>';
    }
  }

  function renderUsers() {
    const host = $a('#hcaUserList');
    if (!host) return;
    host.innerHTML = users.map(user => `
      <div class="hca-user-row" data-user-id="${escA(user.id)}">
        <div><b>${escA(user.display_name || user.username)}</b><span>@${escA(user.username)} · ${user.last_login_at ? 'zuletzt ' + escA(user.last_login_at) : 'noch nie angemeldet'}</span></div>
        <select class="text-input compact" data-user-role ${user.id === currentUser.id ? 'disabled' : ''}><option value="employee" ${user.role === 'employee' ? 'selected' : ''}>Mitarbeiter</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Administrator</option></select>
        <label class="check-line"><input type="checkbox" data-user-active ${user.active ? 'checked' : ''} ${user.id === currentUser.id ? 'disabled' : ''}> Aktiv</label>
        <button class="btn secondary compact" data-user-password type="button">Passwort setzen</button>
        <button class="btn secondary compact" data-user-save type="button" ${user.id === currentUser.id ? 'disabled' : ''}>Speichern</button>
      </div>`).join('');
    host.querySelectorAll('[data-user-save]').forEach(button => button.onclick = () => updateUser(button.closest('[data-user-id]')));
    host.querySelectorAll('[data-user-password]').forEach(button => button.onclick = () => resetUserPassword(button.closest('[data-user-id]')));
  }

  async function createUser() {
    const payload = {
      display_name:$a('#hcaNewUserName').value.trim(),
      username:$a('#hcaNewUsername').value.trim(),
      password:$a('#hcaNewUserPassword').value,
      role:$a('#hcaNewUserRole').value
    };
    try {
      await authApi('users', {method:'POST', body:JSON.stringify(payload)});
      $a('#hcaNewUserName').value = '';
      $a('#hcaNewUsername').value = '';
      $a('#hcaNewUserPassword').value = '';
      await loadUsers();
      alert('Benutzer wurde angelegt.');
    } catch (error) {
      alert('Benutzer konnte nicht angelegt werden:\n' + (error.message || error));
    }
  }

  async function updateUser(row) {
    try {
      await authApi('users/' + encodeURIComponent(row.dataset.userId), {
        method:'PUT',
        body:JSON.stringify({role:row.querySelector('[data-user-role]').value, active:row.querySelector('[data-user-active]').checked})
      });
      await loadUsers();
      alert('Benutzer wurde aktualisiert.');
    } catch (error) {
      alert('Benutzer konnte nicht aktualisiert werden:\n' + (error.message || error));
    }
  }

  async function resetUserPassword(row) {
    const password = await hcaPrompt('Neues Passwort für diesen Benutzer:', '');
    if (!password) return;
    try {
      await authApi('users/' + encodeURIComponent(row.dataset.userId) + '/password', {
        method:'PUT',
        body:JSON.stringify({password})
      });
      alert('Das neue Passwort wurde gespeichert. Bestehende Anmeldungen des Benutzers wurden beendet.');
    } catch (error) {
      alert('Passwort konnte nicht geändert werden:\n' + (error.message || error));
    }
  }

  function insertPersonalSignature() {
    if (!currentUser) return;
    window.setTimeout(() => {
      const editor = $a('#hcaMailRichEditor');
      const textarea = $a('#mailComposeBody');
      if (!editor || !$a('#mailComposeDialog')?.open) return;
      const signature = cleanHtml(currentUser.signature_html || '');
      editor.innerHTML = signature ? '<p><br></p><div class="hca-mail-signature" data-hca-signature>' + signature + '</div>' : '';
      textarea.value = editor.innerText.replace(/\u00a0/g, ' ').trim();
      editor.focus();
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
    }, 20);
  }

  async function initialiseAuthentication() {
    try {
      const status = await authApi('status');
      if (!status.users_configured) {
        window.hcaAuthSession.set('');
        loginShell('bootstrap');
        return;
      }
      if (!status.authenticated) {
        window.hcaAuthSession.set('');
        loginShell('login');
        return;
      }
      currentUser = status.user;
      window.hcaAuthSession.release();
      $a('#hcaLoginOverlay')?.classList.add('hidden');
      addUserChip();
      mountUserSettings();
      $a('#mailCompose')?.addEventListener('click', insertPersonalSignature);
      document.querySelectorAll('[data-view="settings"]').forEach(button => button.addEventListener('click', () => window.setTimeout(mountUserSettings, 0)));
    } catch (error) {
      loginShell('login', 'Der HCA-Server ist nicht erreichbar: ' + (error.message || error));
    }
  }

  document.addEventListener('DOMContentLoaded', initialiseAuthentication);
})();
