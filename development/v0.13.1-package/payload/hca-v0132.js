/* HCA v0.13.2 – Kundenkartei und E-Mail-Erweiterungen */
var hcaCustomerTab = 'overview';

function hcaCustomerCommercial(c = {}) {
  return {
    discount_pct: Number(c.discount_pct ?? c.customer_discount_pct ?? c.discount ?? 0) || 0,
    credit_balance: Number(c.credit_balance ?? c.credit ?? c.customer_credit ?? 0) || 0,
    vouchers: String(c.vouchers ?? c.voucher_codes ?? c.customer_vouchers ?? '')
  };
}

function hcaNormalizeCustomer(c = {}) {
  const billing = c.billing || {};
  const shipping = c.shipping || {};
  return {
    ...c,
    company_name: c.company_name || c.company || billing.company || '',
    first_name: c.first_name || c.billing_first_name || billing.first_name || '',
    last_name: c.last_name || c.billing_last_name || billing.last_name || '',
    email: c.email || c.billing_email || billing.email || '',
    phone: c.phone || c.billing_phone || billing.phone || '',
    billing_street: c.billing_street || [billing.address_1, billing.address_2].filter(Boolean).join(' ') || '',
    billing_zip: c.billing_zip || billing.postcode || '',
    billing_city: c.billing_city || billing.city || '',
    billing_country: c.billing_country || billing.country || 'DE',
    shipping_street: c.shipping_street || [shipping.address_1, shipping.address_2].filter(Boolean).join(' ') || '',
    shipping_zip: c.shipping_zip || shipping.postcode || '',
    shipping_city: c.shipping_city || shipping.city || '',
    shipping_country: c.shipping_country || shipping.country || billing.country || 'DE'
  };
}

function hcaCustomerDocumentRows(rows, kind) {
  if (!rows.length) return '<div class="business-empty compact">Keine Einträge.</div>';
  return '<div class="business-card-list">' + rows.map(x => {
    const no = kind === 'invoice' ? financeDisplayNo(x) : (kind === 'quote' ? x.quote_no : x.order_no);
    const amount = kind === 'invoice' ? x.total_gross : x.totals?.gross;
    const attr = kind === 'invoice' ? 'data-customer-invoice' : (kind === 'quote' ? 'data-customer-quote' : 'data-customer-order');
    return `<button class="business-mini-card" ${attr}="${escapeHtml(x.id)}"><span><b>${escapeHtml(no || '')}</b>${escapeHtml(x.subject || '')}</span><span><strong>${businessMoney(amount)}</strong></span></button>`;
  }).join('') + '</div>';
}

renderBusinessCustomerDetail = function(c) {
  c = hcaNormalizeCustomer(c || {});
  activeBusinessCustomerDetail = c;
  const host = $('#businessCustomerDetail');
  if (!host) return;
  const contacts = c.contacts || [], addresses = c.addresses || [], quotes = c.quotes || [], orders = c.orders || [], invoices = c.invoices || [];
  const commercial = hcaCustomerCommercial(c);
  const tab = (key, label, count = '') => `<button type="button" data-customer-tab="${key}" class="${hcaCustomerTab === key ? 'active' : ''}">${label}${count === '' ? '' : ` <em>${count}</em>`}</button>`;
  const addressesHtml = addresses.length ? addresses.map(a => `<div class="business-address-card"><div><b>${escapeHtml(a.label || 'Adresse')}</b><span>${businessAddressRecordHtml(a)}</span></div><div class="business-card-actions"><div class="business-address-tags">${a.is_default_billing ? '<span class="business-tag">Standard Rechnung</span>' : ''}${a.is_default_shipping ? '<span class="business-tag">Standard Lieferung</span>' : ''}</div><button class="business-mini-action" type="button" data-edit-business-address="${escapeHtml(a.id)}">Bearbeiten</button></div></div>`).join('') : '<div class="business-empty compact">Noch keine Adresse.</div>';
  const contactsHtml = contacts.length ? contacts.map(x => `<div class="business-contact-card"><div><b>${escapeHtml(x.display_name || [x.first_name,x.last_name].filter(Boolean).join(' ') || 'Kontakt')}</b><span>${escapeHtml(x.role || '')}</span><small>${escapeHtml([x.email,x.phone,x.mobile].filter(Boolean).join(' · '))}</small></div><div class="business-card-actions">${x.is_primary ? '<span class="business-tag">Hauptkontakt</span>' : ''}<button class="business-mini-action" type="button" data-edit-business-contact="${escapeHtml(x.id)}">Bearbeiten</button></div></div>`).join('') : '<div class="business-empty compact">Noch kein Ansprechpartner.</div>';
  let panel = '';
  if (hcaCustomerTab === 'contacts') panel = `<div class="panel"><div class="panel-head"><div><div class="eyebrow">ANSPRECHPARTNER</div><h3>Kontakte</h3></div><button class="btn primary" id="businessAddContact" type="button">+ Ansprechpartner</button></div><div class="business-card-list">${contactsHtml}</div></div>`;
  else if (hcaCustomerTab === 'addresses') panel = `<div class="panel"><div class="panel-head"><div><div class="eyebrow">ADRESSBUCH</div><h3>Adressen</h3></div><button class="btn primary" id="businessAddAddress" type="button">+ Adresse</button></div><div class="business-card-list">${addressesHtml}</div></div>`;
  else if (hcaCustomerTab === 'quotes') panel = `<div class="panel"><div class="panel-head"><h3>Angebote</h3><button class="btn primary" id="businessCustomerNewQuoteInline" type="button">+ Angebot</button></div>${hcaCustomerDocumentRows(quotes,'quote')}</div>`;
  else if (hcaCustomerTab === 'orders') panel = `<div class="panel"><div class="panel-head"><h3>Aufträge</h3></div>${hcaCustomerDocumentRows(orders,'order')}</div>`;
  else if (hcaCustomerTab === 'invoices') panel = `<div class="panel"><div class="panel-head"><h3>Rechnungen</h3><button class="btn primary" id="businessCustomerNewInvoice" type="button">+ Rechnung</button></div>${hcaCustomerDocumentRows(invoices,'invoice')}</div>`;
  else if (hcaCustomerTab === 'mail') panel = `<div class="panel"><div class="panel-head"><div><div class="eyebrow">KOMMUNIKATION</div><h3>E-Mail</h3></div><button class="btn primary" id="businessCustomerComposeMail" type="button">+ E-Mail an Kunden</button></div><p class="settings-note">Neue Nachrichten werden mit der Kundenadresse vorbereitet. Der vollständige Posteingang ist über den Hauptpunkt E-Mail erreichbar.</p></div>`;
  else panel = `<div class="business-two-col"><div class="panel"><div class="panel-head"><h3>Stammdaten</h3></div><div class="business-kv"><span>E-Mail</span><b>${escapeHtml(c.email || '–')}</b><span>Telefon</span><b>${escapeHtml(c.phone || '–')}</b><span>Mobil</span><b>${escapeHtml(c.mobile || '–')}</b><span>USt-IdNr.</span><b>${escapeHtml(c.vat_id || '–')}</b><span>Standardkunde</span><b>${c.is_default ? 'Ja' : 'Nein'}</b></div></div><div class="panel"><div class="panel-head"><h3>Konditionen</h3></div><div class="business-kv"><span>Kundenrabatt</span><b>${commercial.discount_pct.toLocaleString('de-DE')} %</b><span>Guthaben</span><b>${businessMoney(commercial.credit_balance)}</b><span>Gutscheine</span><b>${escapeHtml(commercial.vouchers || '–')}</b></div></div></div><div class="business-two-col"><div class="panel"><div class="panel-head"><h3>Rechnungsadresse</h3></div><p>${businessAddressHtml(c,'billing')}</p></div><div class="panel"><div class="panel-head"><h3>Lieferadresse</h3></div><p>${businessAddressHtml(c,'shipping')}</p></div></div>${c.notes ? `<div class="panel"><div class="eyebrow">INTERNE NOTIZ</div><p class="business-note">${escapeHtml(c.notes)}</p></div>` : ''}`;
  host.innerHTML = `<div class="business-object-head"><div><div class="eyebrow">KUNDE · ${escapeHtml(c.customer_no || '')}</div><h2>${escapeHtml(businessCustomerDisplay(c))}</h2><div class="business-object-meta">${escapeHtml([c.email,c.phone,c.billing_city].filter(Boolean).join(' · '))}</div></div><div>${c.is_default ? '<span class="business-status status-ready">Standardkunde</span>' : '<span class="business-status status-accepted">Aktiv</span>'}</div></div><nav class="business-tabs">${tab('overview','Übersicht')}${tab('contacts','Kontakte',contacts.length)}${tab('addresses','Adressen',addresses.length)}${tab('quotes','Angebote',quotes.length)}${tab('orders','Aufträge',orders.length)}${tab('invoices','Rechnungen',invoices.length)}${tab('mail','E-Mails')}</nav><div class="hca-customer-tab-panel">${panel}</div>`;
  host.querySelectorAll('[data-customer-tab]').forEach(b => b.onclick = () => { hcaCustomerTab = b.dataset.customerTab; renderBusinessCustomerDetail(c); });
  $('#businessAddContact')?.addEventListener('click', () => openBusinessContactDialog());
  $('#businessAddAddress')?.addEventListener('click', () => openBusinessAddressDialog());
  $('#businessCustomerNewQuoteInline')?.addEventListener('click', () => openNewBusinessQuote(c.id));
  $('#businessCustomerNewInvoice')?.addEventListener('click', () => openFinanceCustomerInvoiceDialog(c.id));
  $('#businessCustomerComposeMail')?.addEventListener('click', () => { businessOpenView('mail'); setTimeout(() => { $('#mailCompose')?.click(); $('#mailComposeTo').value = c.email || ''; }, 0); });
  host.querySelectorAll('[data-edit-business-contact]').forEach(b => b.onclick = () => openBusinessContactDialog(contacts.find(x => String(x.id) === String(b.dataset.editBusinessContact)) || {}));
  host.querySelectorAll('[data-edit-business-address]').forEach(b => b.onclick = () => openBusinessAddressDialog(addresses.find(x => String(x.id) === String(b.dataset.editBusinessAddress)) || {}));
  host.querySelectorAll('[data-customer-quote]').forEach(b => b.onclick = () => openBusinessQuoteEditor(b.dataset.customerQuote));
  host.querySelectorAll('[data-customer-order]').forEach(b => b.onclick = () => openBusinessSalesOrder(b.dataset.customerOrder));
  host.querySelectorAll('[data-customer-invoice]').forEach(b => b.onclick = () => openFinanceInvoice(b.dataset.customerInvoice));
};

const hcaV132OpenBusinessCustomer = openBusinessCustomer;
openBusinessCustomer = async function(id) {
  hcaCustomerTab = 'overview';
  return hcaV132OpenBusinessCustomer(id);
};

function hcaMailAttachmentList() {
  const input = $('#mailComposeAttachments'), list = $('#mailComposeAttachmentList');
  if (!list) return;
  const files = [...(input?.files || [])];
  list.innerHTML = files.length ? files.map(f => `<span class="business-tag">${escapeHtml(f.name)} · ${Math.ceil(f.size/1024)} KB</span>`).join('') : '<span class="settings-note">Keine Anhänge ausgewählt.</span>';
}

$('#mailComposeAttachments')?.addEventListener('change', hcaMailAttachmentList);
$('#mailCompose')?.addEventListener('click', () => {
  const account = hcaMailAccounts.find(x => String(x.id) === String($('#mailAccountSelect')?.value)) || {};
  const signature = String(account.signature || '').trim();
  $('#mailComposeBody').value = signature ? `\n\n-- \n${signature}` : '';
  if ($('#mailComposeAttachments')) $('#mailComposeAttachments').value = '';
  hcaMailAttachmentList();
});

$('#mailSend')?.addEventListener('click', async e => {
  e.preventDefault();
  e.stopImmediatePropagation();
  const id = $('#mailAccountSelect')?.value;
  if (!id) return alert('Bitte ein Postfach auswählen.');
  const files = [...($('#mailComposeAttachments')?.files || [])];
  const total = files.reduce((n,f) => n + f.size, 0);
  if (total > 20 * 1024 * 1024) return alert('Die Anhänge sind zusammen größer als 20 MB.');
  try {
    const attachments = await Promise.all(files.map(financeFileData));
    await businessApi(`/mail/accounts/${encodeURIComponent(id)}/send`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({to:$('#mailComposeTo').value.trim(),cc:$('#mailComposeCc')?.value.trim() || '',bcc:$('#mailComposeBcc')?.value.trim() || '',subject:$('#mailComposeSubject').value.trim(),message:$('#mailComposeBody').value,attachments}),timeoutMs:120000});
    $('#mailComposeDialog').close();
    alert('E-Mail wurde gesendet.');
  } catch(err) { alert(`E-Mail konnte nicht gesendet werden:\n${err.message || err}`); }
}, true);
