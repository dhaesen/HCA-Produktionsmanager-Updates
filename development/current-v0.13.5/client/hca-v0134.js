'use strict';

/* HCA v0.13.4: Startansicht, Rich-Text-Mail, Printprodukte und Rechnungskorrekturen. */
(() => {
  const $v = selector => document.querySelector(selector);
  const esc = value => escapeHtml(String(value == null ? '' : value));

  function startupSplash() {
    const splash = $v('#hcaStartupSplash');
    if (!splash) return;
    const bar = splash.querySelector('.hca-startup-progress > span');
    const label = splash.querySelector('[data-startup-status]');
    const steps = [
      [18, 'Oberfläche wird vorbereitet …'],
      [42, 'Einstellungen werden geladen …'],
      [68, 'Verbindung wird geprüft …'],
      [88, 'Arbeitsbereiche werden geöffnet …'],
      [100, 'HCA ist bereit.']
    ];
    let index = 0;
    const advance = () => {
      if (!splash.isConnected) return;
      const [percent, text] = steps[index++];
      if (bar) bar.style.width = percent + '%';
      if (label) label.textContent = text;
      if (index < steps.length) window.setTimeout(advance, index === 1 ? 180 : 260);
      else window.setTimeout(() => {
        splash.classList.add('is-finished');
        window.setTimeout(() => splash.remove(), 420);
      }, 180);
    };
    window.setTimeout(advance, 40);
  }

  function sanitizeRichHtml(source) {
    const template = document.createElement('template');
    template.innerHTML = String(source || '');
    const allowed = new Set(['B','STRONG','I','EM','U','S','P','DIV','BR','UL','OL','LI','A','H1','H2','H3','BLOCKQUOTE','SPAN']);
    const walk = node => {
      [...node.children].forEach(child => {
        if (!allowed.has(child.tagName)) {
          child.replaceWith(...child.childNodes);
          return;
        }
        [...child.attributes].forEach(attr => {
          const name = attr.name.toLowerCase();
          if (child.tagName === 'A' && name === 'href') {
            const href = String(attr.value || '').trim();
            if (!/^(https?:|mailto:)/i.test(href)) child.removeAttribute(attr.name);
          } else if (child.tagName === 'A' && name === 'target') {
            child.setAttribute('target', '_blank');
            child.setAttribute('rel', 'noopener');
          } else if (name !== 'style') {
            child.removeAttribute(attr.name);
          } else {
            const safe = String(attr.value || '').split(';').filter(rule => /^\s*(text-align|color|background-color|font-size)\s*:/i.test(rule)).join(';');
            safe ? child.setAttribute('style', safe) : child.removeAttribute('style');
          }
        });
        walk(child);
      });
    };
    walk(template.content);
    return template.innerHTML;
  }

  let richEditor = null;
  function syncRichEditor() {
    const textarea = $v('#mailComposeBody');
    if (!textarea || !richEditor) return;
    textarea.value = richEditor.innerText.replace(/\u00a0/g, ' ').trim();
  }
  function richCommand(command, value = null) {
    richEditor?.focus();
    document.execCommand(command, false, value);
    syncRichEditor();
  }
  function mountRichMailEditor() {
    const textarea = $v('#mailComposeBody');
    if (!textarea || $v('#hcaMailRichEditor')) return;
    textarea.classList.add('hca-rich-source');
    const shell = document.createElement('div');
    shell.className = 'hca-rich-editor';
    shell.innerHTML = `
      <div class="hca-rich-toolbar" role="toolbar" aria-label="Textformatierung">
        <button type="button" data-rich-command="bold" title="Fett"><b>B</b></button>
        <button type="button" data-rich-command="italic" title="Kursiv"><i>I</i></button>
        <button type="button" data-rich-command="underline" title="Unterstrichen"><u>U</u></button>
        <span></span>
        <button type="button" data-rich-block="p">Text</button>
        <button type="button" data-rich-block="h2">Überschrift</button>
        <span></span>
        <button type="button" data-rich-command="insertUnorderedList" title="Aufzählung">• Liste</button>
        <button type="button" data-rich-command="insertOrderedList" title="Nummerierung">1. Liste</button>
        <button type="button" data-rich-link title="Link einfügen">Link</button>
        <span></span>
        <button type="button" data-rich-command="removeFormat">Format löschen</button>
      </div>
      <div id="hcaMailRichEditor" class="hca-rich-content" contenteditable="true" role="textbox" aria-multiline="true"></div>`;
    textarea.insertAdjacentElement('afterend', shell);
    richEditor = shell.querySelector('#hcaMailRichEditor');
    richEditor.addEventListener('input', syncRichEditor);
    shell.querySelectorAll('[data-rich-command]').forEach(button => button.onclick = () => richCommand(button.dataset.richCommand));
    shell.querySelectorAll('[data-rich-block]').forEach(button => button.onclick = () => richCommand('formatBlock', button.dataset.richBlock));
    shell.querySelector('[data-rich-link]').onclick = async () => {
      const href = await hcaPrompt('Vollständige Internetadresse eingeben:', 'https://');
      if (href && /^(https?:|mailto:)/i.test(href)) richCommand('createLink', href);
    };

    $v('#mailCompose')?.addEventListener('click', () => window.setTimeout(() => {
      const plain = String(textarea.value || '');
      richEditor.innerHTML = plain ? esc(plain).replace(/\n/g, '<br>') : '';
      richEditor.focus();
    }, 0));

    const oldButton = $v('#mailSend');
    if (!oldButton) return;
    const sendButton = oldButton.cloneNode(true);
    oldButton.replaceWith(sendButton);
    sendButton.addEventListener('click', async () => {
      const accountId = $v('#mailAccountSelect')?.value;
      if (!accountId) return alert('Bitte ein Postfach auswählen.');
      const files = [...($v('#mailComposeAttachments')?.files || [])];
      if (files.reduce((sum, file) => sum + file.size, 0) > 20 * 1024 * 1024) return alert('Die Anhänge sind zusammen größer als 20 MB.');
      const to = $v('#mailComposeTo')?.value.trim() || '';
      if (!to) return alert('Bitte einen Empfänger eingeben.');
      sendButton.disabled = true;
      try {
        const attachments = await Promise.all(files.map(financeFileData));
        const html = sanitizeRichHtml(richEditor.innerHTML);
        const message = richEditor.innerText.replace(/\u00a0/g, ' ').trim();
        await businessApi(`/mail/accounts/${encodeURIComponent(accountId)}/send`, {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            to,
            cc: $v('#mailComposeCc')?.value.trim() || '',
            bcc: $v('#mailComposeBcc')?.value.trim() || '',
            subject: $v('#mailComposeSubject')?.value.trim() || '',
            message,
            html,
            attachments
          }),
          timeoutMs: 120000
        });
        $v('#mailComposeDialog')?.close();
        alert('E-Mail wurde gesendet.');
      } catch (error) {
        alert(`E-Mail konnte nicht gesendet werden:\n${error.message || error}`);
      } finally {
        sendButton.disabled = false;
      }
    });
  }

  const originalUnifiedPositionHtml = hcaUnifiedPositionHtml;
  hcaUnifiedPositionHtml = function(line, index, locked = false) {
    line.config = line.config || {};
    const type = line.config.product_type || 'textile';
    let html = originalUnifiedPositionHtml(line, index, locked);
    html = html.replace(
      '<option value="service"',
      `<option value="print" ${type === 'print' ? 'selected' : ''}>Printprodukt</option><option value="service"`
    );
    if (type !== 'print') return html;
    html = html.replace(
      /<div class="business-product-search">[\s\S]*?<\/div><div class="business-form-grid quote-line-grid">/,
      '<div class="hca-print-product-banner"><b>Printprodukt</b><span>Manuell kalkulierbare Drucksache ohne Shopartikelsuche</span></div><div class="business-form-grid quote-line-grid">'
    );
    const config = line.config;
    const printFields = `
      <div class="hca-print-product-fields">
        <div class="span-2"><label>Artikelname</label><input class="text-input" data-hca-print-field="print_name" data-hca-print-index="${index}" value="${esc(config.print_name || line.description || '')}" ${locked ? 'disabled' : ''}></div>
        <div class="span-2"><label>Beschreibung</label><textarea class="text-input" rows="3" data-hca-print-field="print_description" data-hca-print-index="${index}" ${locked ? 'disabled' : ''}>${esc(config.print_description || '')}</textarea></div>
        <div><label>Auflage</label><input class="text-input" type="number" min="1" step="1" data-hca-print-field="print_run" data-hca-print-index="${index}" value="${Number(config.print_run || line.quantity) || 1}" ${locked ? 'disabled' : ''}></div>
        <div><label>Druckmedium</label><input class="text-input" data-hca-print-field="print_medium" data-hca-print-index="${index}" placeholder="z. B. 300 g/m² Bilderdruck matt" value="${esc(config.print_medium || '')}" ${locked ? 'disabled' : ''}></div>
      </div>`;
    html = html.replace('<div class="business-line-section business-qty-row">', printFields + '<div class="business-line-section business-qty-row hca-print-quantity-source">');
    return html;
  };
  businessQuoteLineHtml = hcaUnifiedPositionHtml;

  const originalBindPositionForm = hcaBindPositionForm;
  hcaBindPositionForm = function(host, lines, rerender, onTotals = () => {}) {
    originalBindPositionForm(host, lines, rerender, onTotals);
    host?.querySelectorAll('[data-hca-print-field]').forEach(element => {
      element.addEventListener('input', () => {
        const line = lines[Number(element.dataset.hcaPrintIndex)];
        if (!line) return;
        line.config = line.config || {};
        const field = element.dataset.hcaPrintField;
        const value = field === 'print_run' ? Math.max(1, Number(element.value) || 1) : element.value;
        line.config[field] = value;
        if (field === 'print_name') line.description = value;
        if (field === 'print_run') line.quantity = value;
        onTotals();
        hcaPositionSum(host, line, Number(element.dataset.hcaPrintIndex));
      });
    });
  };

  function remountUnifiedDocumentEditors() {
    if ($v('#businessOrderLines') && Array.isArray(HCA103?.orderLines)) hca103RenderOrderLines();
    if ($v('#financeInvoiceLines') && Array.isArray(financeInvoiceLines)) renderFinanceInvoiceLines();
  }

  function ensureCreditDialog() {
    if ($v('#hcaCreditNoteDialog')) return;
    document.body.insertAdjacentHTML('beforeend', `
      <dialog id="hcaCreditNoteDialog" class="hca-credit-dialog">
        <form method="dialog" onsubmit="return false">
          <div class="modal-head">
            <div><div class="eyebrow">RECHNUNGSKORREKTUR</div><h2>Rechnung stornieren</h2></div>
            <button type="button" class="icon-btn" data-credit-close aria-label="Schließen">×</button>
          </div>
          <div class="hca-credit-warning">
            Die festgeschriebene Rechnung bleibt unverändert. HCA erstellt eine vollständige Gutschrift und überträgt sie an Lexware Office.
          </div>
          <div class="business-kv hca-credit-summary" id="hcaCreditSummary"></div>
          <label>Grund der Stornierung</label>
          <textarea id="hcaCreditReason" class="text-input" rows="3" placeholder="Grund für die Rechnungskorrektur"></textarea>
          <fieldset id="hcaCreditSettlement">
            <legend>Behandlung des Gutschriftenbetrags</legend>
            <label><input type="radio" name="hcaCreditSettlement" value="offset"> Mit der offenen Forderung verrechnen</label>
            <label data-paid-only><input type="radio" name="hcaCreditSettlement" value="refund"> Betrag an den Kunden zurückzahlen</label>
            <label data-paid-only><input type="radio" name="hcaCreditSettlement" value="customer_credit"> Als Guthaben auf dem Kundenkonto hinterlegen</label>
          </fieldset>
          <p class="settings-note" id="hcaCreditSettlementNote"></p>
          <div class="modal-actions">
            <button type="button" class="btn secondary" data-credit-close>Abbrechen</button>
            <button type="button" class="btn danger" id="hcaCreateCreditNote">Gutschrift erstellen und Rechnung stornieren</button>
          </div>
        </form>
      </dialog>`);
    document.querySelectorAll('[data-credit-close]').forEach(button => button.onclick = () => $v('#hcaCreditNoteDialog')?.close());
  }

  function invoiceIsPaid(invoice) {
    return ['paid','paidoff'].includes(String(invoice.payment_status || invoice.status || '').toLowerCase()) ||
      (invoice.lexware && Number(invoice.lexware_open_amount) === 0);
  }

  function openCreditDialog(invoice) {
    ensureCreditDialog();
    const dialog = $v('#hcaCreditNoteDialog');
    const paid = invoiceIsPaid(invoice);
    dialog.dataset.invoiceId = invoice.id;
    $v('#hcaCreditReason').value = '';
    $v('#hcaCreditSummary').innerHTML = `<span>Rechnung</span><b>${esc(financeDisplayNo(invoice))}</b><span>Kunde</span><b>${esc(financePartyName(invoice))}</b><span>Gutschrift brutto</span><b>${businessMoney(invoice.total_gross)}</b><span>Zahlungsstatus</span><b>${paid ? 'bereits bezahlt' : 'noch offen'}</b>`;
    dialog.querySelectorAll('[data-paid-only]').forEach(label => label.classList.toggle('hidden', !paid));
    const offset = dialog.querySelector('input[value="offset"]');
    const refund = dialog.querySelector('input[value="refund"]');
    if (paid) {
      offset.checked = false;
      refund.checked = true;
      offset.closest('label').classList.add('hidden');
      $v('#hcaCreditSettlementNote').textContent = 'Die Lexware-Zahlungs-API ist nur lesbar. Eine gewählte Rückzahlung wird deshalb in HCA als ausstehend geführt und nach der Bankzahlung in Lexware zugeordnet.';
    } else {
      offset.closest('label').classList.remove('hidden');
      offset.checked = true;
      $v('#hcaCreditSettlementNote').textContent = 'Die Gutschrift wird in Lexware direkt mit der offenen Forderung verbunden.';
    }
    dialog.showModal();
  }

  async function createCreditNote() {
    const dialog = $v('#hcaCreditNoteDialog');
    const invoiceId = dialog?.dataset.invoiceId;
    const settlement = dialog?.querySelector('input[name="hcaCreditSettlement"]:checked')?.value;
    const reason = $v('#hcaCreditReason')?.value.trim() || '';
    if (!invoiceId || !settlement) return alert('Bitte die Behandlung des Gutschriftenbetrags auswählen.');
    if (!reason) return alert('Bitte einen Grund für die Stornierung angeben.');
    const button = $v('#hcaCreateCreditNote');
    button.disabled = true;
    button.textContent = 'Gutschrift wird erstellt …';
    try {
      const result = await businessApi(`/finance/invoices/${encodeURIComponent(invoiceId)}/credit-note`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({reason, settlement_method:settlement}),
        timeoutMs:90000
      });
      dialog.close();
      await Promise.all([loadFinanceInvoices(), loadBusinessDashboard()]);
      await openFinanceInvoice(invoiceId);
      const method = result.credit_note?.settlement_method;
      alert(method === 'customer_credit'
        ? 'Gutschrift wurde erstellt, an Lexware übertragen und dem Kundenkonto gutgeschrieben.'
        : method === 'refund'
          ? 'Gutschrift wurde erstellt und an Lexware übertragen. Die Rückzahlung ist in HCA als ausstehend markiert.'
          : 'Gutschrift wurde erstellt, an Lexware übertragen und mit der Forderung verrechnet.');
    } catch (error) {
      alert(`Gutschrift konnte nicht erstellt werden:\n${error.message || error}`);
    } finally {
      button.disabled = false;
      button.textContent = 'Gutschrift erstellen und Rechnung stornieren';
    }
  }

  const originalRenderFinanceInvoiceDetail = renderFinanceInvoiceDetail;
  renderFinanceInvoiceDetail = function(invoice = {}) {
    originalRenderFinanceInvoiceDetail(invoice);
    const localFinal = invoice.record_type !== 'external' && invoice.direction === 'customer' && invoice.status !== 'draft';
    const alreadyCancelled = ['voided','cancelled'].includes(String(invoice.status || '')) || invoice.credit_note_id;
    const actions = $v('#financeInvoiceTopActions');
    if (localFinal && !alreadyCancelled && actions) {
      const button = document.createElement('button');
      button.className = 'btn danger';
      button.type = 'button';
      button.textContent = 'Rechnung stornieren';
      button.onclick = () => openCreditDialog(invoice);
      actions.appendChild(button);
    }
    if (invoice.credit_note_id) {
      const detail = $v('#financeInvoiceDetail');
      detail?.insertAdjacentHTML('afterbegin', `<div class="hca-credit-linked"><b>Storniert durch Gutschrift ${esc(invoice.credit_note_no || '')}</b><span>${esc(invoice.credit_settlement_label || '')}</span>${invoice.credit_lexware_deeplink ? `<a href="${esc(invoice.credit_lexware_deeplink)}" target="_blank" rel="noopener">In Lexware Office öffnen</a>` : ''}</div>`);
    }
  };

  $v('#hcaCreateCreditNote')?.addEventListener('click', createCreditNote);
  document.addEventListener('DOMContentLoaded', () => {
    startupSplash();
    mountRichMailEditor();
    ensureCreditDialog();
    $v('#hcaCreateCreditNote')?.addEventListener('click', createCreditNote);
    window.setTimeout(remountUnifiedDocumentEditors, 500);
  });
})();
