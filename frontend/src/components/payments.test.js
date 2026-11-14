import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  checkout,
  loadCheckout,
  paymentLabel,
  paymentPermissions,
  toPaise,
  uploadRentalEvidence,
  apiErrorMessage,
  returnReviewState,
  downloadPaymentDocument,
  handoverGuidance,
  submitFinancialAction,
  refundReviewLabel,
} from './paymentFlow.js';
import { invalidateSession, watchSessionChanges } from '../context/sessionSync.js';
import apiClient from '../api/client.js';
import { uploadEvidenceFiles } from './rentalEvidenceUpload.js';
import PaymentModal from './PaymentModal.jsx';
import EscrowStatusCard from './EscrowStatusCard.jsx';
import DisputeResolutionModal from './DisputeResolutionModal.jsx';
import RefundPanel from './RefundPanel.jsx';
import FinancialTimeline from './FinancialTimeline.jsx';
import PaymentDocuments from './PaymentDocuments.jsx';
import Button from './ui/Button.jsx';
import Input from './ui/Input.jsx';

test('only a 401 for the current session clears identity and broadcasts invalidation', () => {
  let token = 'new-session';
  const events = [];
  const browser = {
    localStorage: {
      getItem: () => token,
      removeItem: () => {
        token = null;
      },
    },
    dispatchEvent: (event) => events.push(event.type),
  };
  assert.equal(invalidateSession(browser, 'old-session'), false);
  assert.equal(invalidateSession(browser, null), false);
  assert.equal(token, 'new-session');
  assert.deepEqual(events, []);
  assert.equal(invalidateSession(browser, 'new-session'), true);
  assert.equal(token, null);
  assert.deepEqual(events, ['auth:invalidated']);
  assert.equal(invalidateSession(browser, 'new-session'), false);
});

test('admin review distinguishes refund authorization, dispatch and confirmation', () => {
  assert.match(refundReviewLabel({ status: 'created' }), /authorized.*awaiting dispatch approval/i);
  assert.match(refundReviewLabel({ status: 'pending' }), /awaiting gateway confirmation/);
  assert.match(refundReviewLabel({ status: 'unknown' }), /reconcile before retry/);
  assert.equal(refundReviewLabel({ status: 'processed' }), '');
  assert.equal(refundReviewLabel(null), '');
});

test('financial actions refresh saved state after a lost response without retrying dispatch', async () => {
  const lostResponse = new Error('Synthetic response lost');
  const requests = [];
  let booking;
  let rental;
  const api = {
    post: async (path, payload) => {
      requests.push({ path, payload });
      throw lostResponse;
    },
  };
  await assert.rejects(
    submitFinancialAction(
      api,
      '/payments/refunds/execute',
      { booking_id: 'booking', gateway_refund_approved: true },
      async (options) => {
        assert.equal(options.strict, true);
        booking = { refund: { status: 'processed' } };
      },
      async (options) => {
        assert.equal(options.strict, true);
        rental = { status: 'closed' };
      },
    ),
    (error) => error === lostResponse,
  );
  assert.equal(requests.length, 1);
  assert.equal(booking.refund.status, 'processed');
  assert.equal(rental.status, 'closed');
});

test('financial refresh failures remain visible and still refresh the rental', async () => {
  let rentalRefreshed = false;
  const unavailable = new Error('Synthetic status unavailable');
  await assert.rejects(
    submitFinancialAction(
      { post: async () => ({ data: {} }) },
      '/payments/refunds/reconcile',
      { booking_id: 'booking' },
      async () => {
        throw unavailable;
      },
      async () => {
        rentalRefreshed = true;
      },
    ),
    (error) => error === unavailable,
  );
  assert.equal(rentalRefreshed, true);
});

test('other tabs changing the login invalidate account state; unrelated storage does not', () => {
  const listeners = new Map();
  const browser = {
    localStorage: {},
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: (name, fn) => {
      assert.equal(listeners.get(name), fn);
      listeners.delete(name);
    },
  };
  let resets = 0;
  const stop = watchSessionChanges(browser, () => {
    resets += 1;
  });
  const emit = (key, oldValue, newValue, storageArea = browser.localStorage) =>
    listeners.get('storage')({ key, oldValue, newValue, storageArea });
  emit('nl_token', 'synthetic-a', 'synthetic-b');
  emit('nl_token', 'synthetic-b', null);
  emit(null, null, null);
  assert.equal(resets, 3);
  emit('theme', 'light', 'dark');
  emit('nl_token', 'same', 'same');
  emit('nl_token', null, 'synthetic', {});
  assert.equal(resets, 3);
  stop();
  assert.equal(listeners.size, 0);
});

test('unsent gateway refunds explain dispatch approval and disable premature reconciliation', () => {
  const markup = renderToStaticMarkup(
    React.createElement(RefundPanel, {
      booking: {
        provider: 'razorpay_test',
        rental_fee_paise: 50000,
        refund: {
          id: 'intent',
          status: 'created',
          kind: 'clean_return',
          amount_paise: 340000,
          deduction_paise: 0,
        },
      },
      user: { id: 'admin', is_admin: true },
      allowed: true,
      busy: false,
    }),
  );
  assert.match(markup, /not yet sent to Razorpay/);
  assert.match(markup, /<button[^>]*disabled=""[^>]*>Reconcile refund status/);
  assert.match(markup, /<button[^>]*disabled=""[^>]*>Send approved Test refund/);
  assert.match(markup, /3,400/);
  assert.match(markup, /500/);
});

test('upstream buttons keep labels, icons, submit behavior and native disabled state', () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Button,
      { type: 'submit', disabled: true },
      React.createElement('span', null, 'Confirm handover complete'),
    ),
  );
  assert.match(markup, /type="submit"/);
  assert.match(markup, /disabled=""/);
  assert.match(markup, /btn--primary/);
  assert.match(markup, /Confirm handover complete/);
  const anchor = renderToStaticMarkup(
    React.createElement(Button, { href: '/browse' }, 'Browse items'),
  );
  assert.match(anchor, /href="\/browse"/);
  assert.match(anchor, />Browse items<\/a>/);
});

test('upstream select renders its real category options without crashing', () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      Input,
      { type: 'select', name: 'category', label: 'Category', defaultValue: 'Tools' },
      React.createElement('option', { value: 'Tools' }, 'Tools'),
      React.createElement('option', { value: 'Other' }, 'Other'),
    ),
  );
  assert.match(markup, /<select/);
  assert.match(markup, /selected="">Tools/);
  assert.match(markup, />Other<\/option>/);
});

test('handover explains the actual owner and both confirmation stages', () => {
  const rental = {
    listing_id: 'listing',
    borrower_id: 'aarav',
    lender_id: 'priya',
    lender_username: 'priya_sharma',
    handover_status: 'pending',
  };
  const paid = { handover_unlocked: true };
  assert.match(
    handoverGuidance(rental, { id: 'aarav' }, paid, true),
    /Waiting for priya_sharma to upload/,
  );
  assert.match(
    handoverGuidance(rental, { id: 'priya', is_admin: true }, paid, true),
    /Upload product photos/,
  );
  assert.match(
    handoverGuidance(rental, { id: 'rohan' }, paid, true),
    /Only this rental's borrower and lender/,
  );
  assert.match(
    handoverGuidance(
      { ...rental, handover_status: 'photos_uploaded' },
      { id: 'aarav' },
      paid,
      true,
    ),
    /confirm receipt/,
  );
  assert.match(
    handoverGuidance(
      { ...rental, handover_status: 'borrower_confirmed' },
      { id: 'priya' },
      paid,
      true,
    ),
    /Confirm the handover/,
  );
});

test('handover remains locked when authoritative payment status is unavailable or unverified', () => {
  const rental = {
    listing_id: 'listing',
    borrower_id: 'borrower',
    lender_id: 'lender',
    handover_status: 'pending',
  };
  for (const [booking, unlocked] of [
    [null, false],
    [{ handover_unlocked: false }, false],
    [{ handover_unlocked: true }, false],
  ]) {
    assert.match(handoverGuidance(rental, { id: 'lender' }, booking, unlocked), /stays locked/);
  }
});

const base = {
  id: 'booking',
  borrower_id: 'borrower',
  lender_id: 'lender',
  provider: 'mock',
  sandbox_only: true,
  test_mode: true,
  operations_enabled: true,
  rental_fee_paise: 40000,
  security_deposit_paise: 50000,
  total_amount_paise: 90000,
};

const testOrder = {
  provider: 'razorpay_test',
  sandbox_only: true,
  test_mode: true,
  booking_id: 'booking',
  key_id: 'rzp_test_fixture',
  order_id: 'order_fixture',
  amount_paise: 90000,
  currency: 'INR',
};

test('payment documents appear only for capture and confirmed refunds', () => {
  const render = (booking) =>
    renderToStaticMarkup(React.createElement(PaymentDocuments, { booking, api: {} }));
  assert.equal(render(base), '');
  assert.match(render({ ...base, payment_status: 'captured' }), /Download payment receipt/);
  assert.doesNotMatch(
    render({ ...base, payment_status: 'captured', refund: { status: 'pending' } }),
    /Download refund acknowledgment/,
  );
  assert.match(
    render({ ...base, payment_status: 'captured', refund: { status: 'processed' } }),
    /Download refund acknowledgment/,
  );
});

test('document downloads use authenticated API blob and revoke the object URL', async () => {
  const previousDocument = globalThis.document;
  const create = URL.createObjectURL;
  const revoke = URL.revokeObjectURL;
  const previousTimer = globalThis.setTimeout;
  const calls = [];
  const link = { click: () => calls.push('click'), remove: () => calls.push('remove') };
  globalThis.document = {
    createElement: () => link,
    body: { appendChild: () => calls.push('append') },
  };
  URL.createObjectURL = () => 'blob:synthetic';
  URL.revokeObjectURL = (url) => calls.push(url);
  globalThis.setTimeout = (callback) => callback();
  try {
    const api = {
      get: async (path, options) => {
        assert.equal(path, '/payments/bookings/booking/refund-acknowledgment');
        assert.equal(options.responseType, 'blob');
        return { data: new Blob(['receipt']) };
      },
    };
    await downloadPaymentDocument(api, 'booking', true);
    assert.equal(link.download, 'neighborlend-refund-acknowledgment-booking.html');
    assert.deepEqual(calls, ['append', 'click', 'remove', 'blob:synthetic']);
    await assert.rejects(
      downloadPaymentDocument(
        {
          get: async () => {
            throw { response: { data: new Blob(['{"detail":"Not authorized"}']) } };
          },
        },
        'booking',
      ),
      (error) => apiErrorMessage(error, '') === 'Not authorized',
    );
  } finally {
    globalThis.document = previousDocument;
    URL.createObjectURL = create;
    URL.revokeObjectURL = revoke;
    globalThis.setTimeout = previousTimer;
  }
});

test('exact paise conversion rejects ambiguous/invalid input', () => {
  assert.equal(toPaise('200.05'), 20005);
  assert.equal(toPaise('0'), 0);
  for (const value of ['1.001', '-1', 'NaN', '1e3', '']) assert.throws(() => toPaise(value));
});

test('mock checkout never loads Razorpay or fabricates a verified callback', async () => {
  const calls = [];
  const result = await checkout(
    {
      post: async (...args) => {
        calls.push(args);
        return {
          data: { ...testOrder, provider: 'mock', key_id: null, order_id: 'order_mock_fixture' },
        };
      },
    },
    'booking',
    () => assert.fail('mock mode contacted Razorpay'),
  );
  assert.equal(result.mock, true);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], [
    '/payments/create-order',
    { booking_id: 'booking', accepted_terms: true },
  ]);
});

for (const scenario of ['success', 'failed', 'dismissed', 'unavailable', 'verify-failed']) {
  test(`Razorpay hosted test checkout ${scenario}`, async () => {
    const calls = [];
    const api = {
      post: async (path, data) => {
        calls.push([path, data]);
        if (path.endsWith('create-order')) return { data: testOrder };
        if (scenario === 'verify-failed') throw new Error('server rejected signature');
        return { data: { payment_status: 'captured' } };
      },
    };
    class Widget {
      constructor(options) {
        this.options = options;
        assert.equal(options.amount, 90000);
      }
      on(event, handler) {
        this.failure = handler;
      }
      open() {
        if (scenario === 'failed') this.failure();
        else if (scenario === 'dismissed') this.options.modal.ondismiss();
        else
          this.options.handler({
            razorpay_order_id: 'order_fixture',
            razorpay_payment_id: 'pay_fixture',
            razorpay_signature: 'a'.repeat(64),
          });
      }
    }
    const loader = async () => {
      if (scenario === 'unavailable') throw new Error('unavailable');
      return Widget;
    };
    if (scenario === 'success') {
      const result = await checkout(api, 'booking', loader);
      assert.equal(result.booking.payment_status, 'captured');
      assert.equal(calls[1][0], '/payments/verify');
      assert.equal(calls[1][1].payment_id, 'pay_fixture');
    } else await assert.rejects(checkout(api, 'booking', loader));
  });
}

test('live key or unknown provider is rejected before loading checkout', async () => {
  await assert.rejects(
    checkout(
      { post: async () => ({ data: { ...testOrder, key_id: 'rzp_live_no' } }) },
      'booking',
      () => assert.fail('live checkout loaded'),
    ),
  );
});

test('concurrent checkout script loads share completion and failed loads can retry', async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  let script = null;
  let appended = 0;
  globalThis.window = {};
  globalThis.document = {
    querySelector: () => script,
    createElement: () => ({
      dataset: {},
      remove() {
        script = null;
      },
    }),
    head: {
      appendChild(node) {
        script = node;
        appended += 1;
      },
    },
  };
  try {
    const first = loadCheckout();
    const second = loadCheckout();
    assert.equal(first, second);
    assert.equal(appended, 1);
    window.Razorpay = class Widget {};
    script.onload();
    assert.deepEqual(await Promise.all([first, second]), [window.Razorpay, window.Razorpay]);
    delete window.Razorpay;
    const failed = loadCheckout();
    script.onerror();
    await assert.rejects(failed, /unavailable/);
    const retry = loadCheckout();
    assert.equal(appended, 2);
    window.Razorpay = class Widget {};
    script.onload();
    assert.equal(await retry, window.Razorpay);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test('invalid checkout money is rejected before loading hosted checkout', async () => {
  for (const values of [
    { amount_paise: 1.5, currency: 'INR' },
    { amount_paise: 90000, currency: 'USD' },
    { amount_paise: -1, currency: 'INR' },
    { amount_paise: true, currency: 'INR' },
  ]) {
    await assert.rejects(
      checkout({ post: async () => ({ data: { ...testOrder, ...values } }) }, 'booking', () =>
        assert.fail('invalid money loaded checkout'),
      ),
      /amount or currency/,
    );
  }
});

test('server sandbox confirmation must be explicit and match the booking', async () => {
  for (const changes of [
    { sandbox_only: undefined },
    { sandbox_only: false },
    { sandbox_only: 'true' },
    { test_mode: false },
    { test_mode: undefined },
    { booking_id: 'other' },
    { booking_id: undefined },
    { provider: 'razorpay_live' },
    { provider: 'disabled' },
    { order_id: 'https://attacker.invalid' },
  ]) {
    await assert.rejects(
      checkout({ post: async () => ({ data: { ...testOrder, ...changes } }) }, 'booking', () =>
        assert.fail('unconfirmed checkout loaded'),
      ),
    );
  }
  for (const changes of [
    { sandbox_only: false },
    { sandbox_only: undefined },
    { test_mode: false },
  ]) {
    const booking = { ...base, ...changes, booking_status: 'awaiting_payment' };
    assert.equal(paymentPermissions(booking, { id: 'borrower' }, {}).checkout, false);
    const html = renderToStaticMarkup(
      React.createElement(PaymentModal, { booking, api: {}, onChange() {} }),
    );
    assert.match(html, /Checkout is blocked/);
    assert.match(html, /disabled/);
  }
  const html = renderToStaticMarkup(
    React.createElement(PaymentModal, {
      booking: { ...base, provider: 'razorpay_test' },
      api: {},
      onChange() {},
    }),
  );
  assert.match(html, /RAZORPAY TEST MODE — NO REAL MONEY/);
});

test('duplicate checkout shares one backend request and hosted dialog', async () => {
  let options;
  let posts = 0;
  let dialogs = 0;
  const api = {
    post: async () => {
      posts += 1;
      return { data: testOrder };
    },
  };
  class Widget {
    constructor(value) {
      options = value;
      dialogs += 1;
    }
    on() {}
    open() {}
  }
  const one = checkout(api, 'booking', async () => Widget);
  const two = checkout(api, 'booking', () => assert.fail('second loader started'));
  assert.equal(one, two);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(posts, 1);
  assert.equal(dialogs, 1);
  options.modal.ondismiss();
  await assert.rejects(one, /dismissed/);
  await assert.rejects(two, /dismissed/);
  assert.equal(posts, 1); // Dismissal did not send verification or alter funding.
});

test('dismissal prevents a late callback from submitting verification', async () => {
  const paths = [];
  let options;
  const api = {
    post: async (path) => {
      paths.push(path);
      return { data: testOrder };
    },
  };
  class Widget {
    constructor(value) {
      options = value;
    }
    on() {}
    open() {
      options.modal.ondismiss();
    }
  }
  await assert.rejects(
    checkout(api, 'booking', async () => Widget),
    /dismissed/,
  );
  await options.handler({
    razorpay_order_id: 'order_fixture',
    razorpay_payment_id: 'pay_fixture',
    razorpay_signature: 'a'.repeat(64),
  });
  assert.deepEqual(paths, ['/payments/create-order']);
});

test('tampered callback cannot change order association or bypass backend verification', async () => {
  for (const result of [
    {
      razorpay_order_id: 'order_other',
      razorpay_payment_id: 'pay_fixture',
      razorpay_signature: 'a'.repeat(64),
    },
    {
      razorpay_order_id: 'order_fixture',
      razorpay_payment_id: 'pay_fixture',
      razorpay_signature: 'forged',
    },
  ]) {
    const paths = [];
    const api = {
      post: async (path) => {
        paths.push(path);
        return { data: testOrder };
      },
    };
    class Widget {
      constructor(value) {
        this.options = value;
      }
      on() {}
      open() {
        this.options.handler(result);
      }
    }
    await assert.rejects(
      checkout(api, 'booking', async () => Widget),
      /Invalid checkout result/,
    );
    assert.deepEqual(paths, ['/payments/create-order']);
  }
});

test('checkout forwards only provider identifiers and HMAC to the backend', async () => {
  let submitted;
  const api = {
    post: async (path, data) => {
      if (path.endsWith('create-order')) return { data: testOrder };
      submitted = data;
      return { data: { payment_status: 'captured' } };
    },
  };
  class Widget {
    constructor(value) {
      this.options = value;
    }
    on() {}
    open() {
      this.options.handler({
        razorpay_order_id: 'order_fixture',
        razorpay_payment_id: 'pay_fixture',
        razorpay_signature: 'a'.repeat(64),
        card_number: 'synthetic-must-be-dropped',
        otp: 'synthetic',
        upi_pin: 'synthetic',
        banking_password: 'synthetic',
      });
    }
  }
  await checkout(api, 'booking', async () => Widget);
  assert.deepEqual(Object.keys(submitted).sort(), [
    'booking_id',
    'order_id',
    'payment_id',
    'signature',
  ]);
});

test('payment/refund/legacy labels never imply regulated escrow', () => {
  assert.match(paymentLabel({ payment_status: 'unpaid' }), /handover locked/);
  assert.match(
    paymentLabel({ payment_status: 'captured', deposit_state: 'frozen' }),
    /Dispute pending/,
  );
  assert.match(paymentLabel({ refund: { status: 'pending' } }), /Refund pending/);
  assert.match(paymentLabel({ booking_status: 'completed' }), /Settlement completed/);
  assert.match(paymentLabel({ legacy: true }), /review required/);
});

test('checkout and rental HTML expose test labels, summary and safe loading state', () => {
  const modal = renderToStaticMarkup(
    React.createElement(PaymentModal, { booking: base, api: {}, onChange() {} }),
  );
  assert.match(modal, /refundable deposit/);
  assert.match(modal, /Local demo simulator/);
  assert.match(modal, /Pay test rental/);
  const status = renderToStaticMarkup(
    React.createElement(EscrowStatusCard, {
      request: { id: 'rental' },
      user: { id: 'borrower' },
      api: {},
      onStatus() {},
    }),
  );
  assert.match(status, /TEST MODE/);
  assert.match(status, /not regulated escrow/);
  assert.match(status, /Loading payment status/);
});

test('dispute HTML preserves human consent and missing AI evidence', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: {
        ...base,
        dispute: {
          status: 'raised',
          claimed_deduction_paise: 20000,
          lender_claim_notes: '<script>untrusted</script>',
          borrower_accepted: false,
        },
      },
      user: { id: 'borrower' },
      api: {},
      onChange() {},
      returnReady: true,
    }),
  );
  assert.match(html, /Agree to exact claimed amount/);
  assert.match(html, /No linked inspection/);
  assert.match(html, /No AI finding authorizes a deduction/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /Authorize mutually agreed settlement/);
});

test('disabled payment mode hides dispatch controls while preserving review', () => {
  const row = { ...base, operations_enabled: false, booking_status: 'awaiting_payment' };
  const actions = paymentPermissions(row, { id: 'borrower' }, { handover_status: 'pending' });
  assert.equal(actions.checkout, false);
  assert.equal(actions.reconcile, false);
  assert.equal(actions.refund, false);
  assert.equal(actions.cancel, true);
});

test('financial controls are hidden from outsiders and lender cannot reconcile checkout', () => {
  const row = {
    ...base,
    operations_enabled: true,
    provider: 'razorpay_test',
    booking_status: 'awaiting_payment',
    payment_status: 'unpaid',
  };
  const request = { handover_status: 'pending' };
  for (const value of Object.values(paymentPermissions(row, { id: 'outsider' }, request)))
    assert.equal(Boolean(value), false);
  assert.equal(paymentPermissions(row, { id: 'lender' }, request).reconcile, false);
  assert.equal(paymentPermissions(row, { id: 'borrower' }, request).checkout, true);
});

test('cancelled booking retains eligible refund recovery controls', () => {
  const row = {
    ...base,
    operations_enabled: true,
    booking_status: 'cancelled',
    refund: { status: 'pending' },
  };
  const actions = paymentPermissions(
    row,
    { id: 'admin', is_admin: true },
    { handover_status: 'pending' },
  );
  assert.equal(actions.checkout, false);
  assert.equal(actions.refund, true);
  assert.equal(paymentLabel(row), 'Refund pending');
  assert.equal(
    paymentPermissions({ ...row, refund: { status: 'processed' } }, { id: 'borrower' }, {}).refund,
    false,
  );
});

test('rejected claims show mandatory platform review without borrower acceptance', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: { ...base, dispute: { status: 'escalated', claimed_deduction_paise: 20000 } },
      user: { id: 'borrower' },
      api: {},
      onChange() {},
      returnReady: true,
    }),
  );
  assert.match(html, /Only a platform administrator/);
  assert.doesNotMatch(html, /Agree to exact claimed amount/);
  assert.doesNotMatch(html, /Authorize mutually agreed settlement/);
});

test('administrator can review draft claims with mandatory reason and bounded allocation', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: { ...base, dispute: { status: 'needs_claim', claimed_deduction_paise: 0 } },
      user: { id: 'admin', is_admin: true },
      api: {},
      onChange() {},
      returnReady: true,
    }),
  );
  assert.match(html, /Administrator resolution reason \(required\)/);
  assert.match(html, /Record administrator settlement decision/);
  assert.match(html, /disabled/);
});

test('rental photographs use authenticated rental-specific upload contract', async () => {
  const calls = [];
  const api = {
    post: async (...args) => {
      calls.push(args);
      return { data: { url: '/api/payments/evidence/synthetic-id' } };
    },
  };
  const result = await uploadRentalEvidence(
    api,
    'booking',
    new Blob(['synthetic image'], { type: 'image/png' }),
    'return',
  );
  assert.equal(calls[0][0], '/payments/bookings/booking/evidence?stage=return');
  assert.ok(calls[0][1] instanceof FormData);
  assert.equal(result, '/api/payments/evidence/synthetic-id');
  await assert.rejects(uploadRentalEvidence(api, null, new Blob(), 'return'));
});

test('private evidence helper uses shared authenticated API and leaves multipart boundary to Axios', async () => {
  const oldStorage = globalThis.localStorage;
  const oldAdapter = apiClient.defaults.adapter;
  const oldBaseURL = apiClient.defaults.baseURL;
  let captured;
  let body = '';
  const server = createServer((request, response) => {
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      captured = { method: request.method, url: request.url, headers: request.headers };
      body = Buffer.concat(chunks).toString('latin1');
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ id: 'evidence-1', url: '/api/payments/evidence/evidence-1' }));
    });
  });
  globalThis.localStorage = { getItem: (key) => key === 'nl_token' ? 'test-session-token' : null };
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  apiClient.defaults.baseURL = `http://127.0.0.1:${server.address().port}/api`;
  apiClient.defaults.adapter = 'http';
  try {
    const file = new Blob(['private image bytes'], { type: 'image/png' });
    const refs = await uploadEvidenceFiles(apiClient, 'booking-123', [file], 'handover');
    assert.deepEqual(refs, ['/api/payments/evidence/evidence-1']);
    assert.equal(captured.method, 'POST');
    assert.equal(captured.url, '/api/payments/bookings/booking-123/evidence?stage=handover');
    assert.equal(captured.headers.authorization, 'Bearer test-session-token');
    assert.match(captured.headers['content-type'], /^multipart\/form-data; boundary=/);
    assert.match(body, /name="file"; filename="blob"/);
    assert.match(body, /Content-Type: image\/png/i);
    assert.ok(body.includes('private image bytes'));
  } finally {
    apiClient.defaults.adapter = oldAdapter;
    apiClient.defaults.baseURL = oldBaseURL;
    if (oldStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = oldStorage;
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test('private evidence upload rejects missing booking and malformed backend response', async () => {
  await assert.rejects(uploadEvidenceFiles({ post: async () => assert.fail('no request expected') }, null, [new Blob(['x'])], 'return'), /Verified rental booking/);
  await assert.rejects(uploadEvidenceFiles({ post: async () => ({ data: {} }) }, 'booking', [new Blob(['x'])], 'return'), /private evidence reference/);
});

test('administrator handover recovery controls require an explicit reason', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: base,
      request: { handover_status: 'issue_reported' },
      user: { is_admin: true },
      api: {},
      onChange() {},
    }),
  );
  assert.match(html, /Resume confirmation sequence/);
  assert.match(html, /Permit return photographs/);
  assert.match(html, /Item recovered: cancel and refund/);
});

test('refund breakdown uses backend paise and requires distinct gateway approval', () => {
  for (const [deduction, amount] of [
    [0, 200000],
    [60000, 140000],
  ]) {
    const html = renderToStaticMarkup(
      React.createElement(RefundPanel, {
        booking: {
          ...base,
          provider: 'razorpay_test',
          rental_fee_paise: 50000,
          refund: {
            id: 'intent',
            status: 'created',
            kind: 'dispute',
            amount_paise: amount,
            deduction_paise: deduction,
          },
        },
        user: { id: 'admin', is_admin: true },
        busy: false,
        allowed: true,
        onAction() {},
      }),
    );
    assert.match(html, /Authorized refund to borrower/);
    assert.match(html, deduction ? /₹1,400\.00/ : /₹2,000\.00/);
    assert.match(html, /₹500\.00/);
    assert.match(html, /Reconcile refund status \(no new refund\)/);
    assert.match(html, /I approve a Razorpay Test refund/);
    assert.match(html, /disabled="">Send approved Test refund/);
    assert.match(html, /No lender payout is sent/);
  }
});

test('refund pending, failure, success and outsider states show safe controls', () => {
  for (const status of ['pending', 'failed', 'processed', 'unknown']) {
    const props = {
      booking: {
        ...base,
        provider: 'razorpay_test',
        refund: {
          status,
          amount_paise: 200000,
          deduction_paise: 0,
          kind: 'clean_return',
          error_code: 'provider_notice',
        },
      },
      user: { id: 'admin', is_admin: true },
      busy: true,
      allowed: true,
      onAction() {},
    };
    const html = renderToStaticMarkup(React.createElement(RefundPanel, props));
    assert.match(html, /aria-busy="true"/);
    if (status === 'pending') assert.doesNotMatch(html, /Send approved|Retry same/);
    if (status === 'failed') assert.match(html, /Administrator: retry confirmed failed/);
    if (status === 'processed') assert.doesNotMatch(html, /<button/);
    const outsider = renderToStaticMarkup(
      React.createElement(RefundPanel, { ...props, allowed: false }),
    );
    assert.doesNotMatch(outsider, /<button|checkbox/);
  }
});

test('borrowers and lenders can read refund status but cannot operate it even if allowed is stale', () => {
  const booking = {
    ...base,
    operations_enabled: true,
    refund: { status: 'created', amount_paise: 200000, deduction_paise: 0, kind: 'clean_return' },
  };
  for (const id of ['borrower', 'lender']) {
    assert.equal(paymentPermissions(booking, { id }, {}).refund, false);
    const html = renderToStaticMarkup(
      React.createElement(RefundPanel, {
        booking,
        user: { id, is_admin: false },
        allowed: true,
        busy: false,
        onAction() {},
      }),
    );
    assert.match(html, /Only an administrator can send or reconcile/);
    assert.doesNotMatch(html, /<button|checkbox/);
    assert.match(html, /Authorized refund to borrower/);
  }
});

test('pending gateway refund explains provider confirmation and shows its saved reference', () => {
  const html = renderToStaticMarkup(
    React.createElement(RefundPanel, {
      booking: {
        ...base,
        provider: 'razorpay_test',
        refund: {
          status: 'pending',
          amount_paise: 200000,
          deduction_paise: 0,
          kind: 'clean_return',
          provider_refund_id: 'rfnd_fixture',
        },
      },
      user: { id: 'admin', is_admin: true },
      allowed: true,
      busy: false,
      onAction() {},
    }),
  );
  assert.match(html, /has not confirmed completion/);
  assert.match(html, /Do not send another refund/);
  assert.match(html, /Test Mode does not credit a real bank account/);
  assert.match(html, /rfnd_fixture/);
  assert.doesNotMatch(html, /Send approved Test refund/);
});

test('borrower agreement cannot give either party deduction approval', () => {
  for (const id of ['borrower', 'lender']) {
    const html = renderToStaticMarkup(
      React.createElement(DisputeResolutionModal, {
        booking: {
          ...base,
          dispute: { status: 'raised', borrower_accepted: true, claimed_deduction_paise: 60000 },
        },
        user: { id, is_admin: true },
        api: {},
        onChange() {},
        returnReady: true,
      }),
    );
    assert.match(html, /independent human administrator/);
    assert.doesNotMatch(
      html,
      /Record administrator settlement decision|Authorize mutually agreed settlement/,
    );
  }
});

test('journal presentation totals each posting and flags an imbalance', () => {
  for (const credit of [250000, 249999]) {
    const html = renderToStaticMarkup(
      React.createElement(FinancialTimeline, {
        booking: {
          transactions: [],
          audit: [],
          journal: [
            {
              journal_id: 'funding',
              side: 'DEBIT',
              account: 'gateway_clearing',
              amount_paise: 250000,
            },
            { journal_id: 'funding', side: 'CREDIT', account: 'deposit', amount_paise: credit },
          ],
        },
      }),
    );
    assert.match(html, /₹2,500\.00/);
    assert.match(html, credit === 250000 ? /Balanced/ : /role="alert"/);
  }
});

test('administrator dispute recovery distinguishes pre-receipt cancellation from received-item return', () => {
  for (const handover_status of ['pending', 'borrower_confirmed']) {
    const html = renderToStaticMarkup(
      React.createElement(DisputeResolutionModal, {
        booking: { ...base, dispute: { status: 'escalated', claimed_deduction_paise: 0 } },
        request: {
          handover_status,
          handover_confirmed_at:
            handover_status === 'borrower_confirmed' ? '2026-11-11T00:00:00' : null,
        },
        user: { id: 'admin', is_admin: true },
        api: {},
        onChange() {},
      }),
    );
    assert.match(
      html,
      handover_status === 'pending'
        ? /Item recovered: cancel and refund/
        : /Permit return photographs/,
    );
    assert.doesNotMatch(html, /Resume confirmation sequence/);
  }
});

test('saved raised claim shows amount/version confirmation and prefilled revision fields', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: {
        ...base,
        dispute: {
          id: 'existing',
          status: 'raised',
          claim_version: 3,
          claimed_deduction_paise: 60000,
          lender_claim_notes: 'Damage observed at return',
          borrower_accepted: false,
        },
      },
      user: { id: 'lender' },
      api: {},
      onChange() {},
      returnReady: true,
    }),
  );
  assert.match(html, /Saved claim ₹600\.00, version 3/);
  assert.match(html, /no deduction is approved/);
  assert.match(html, /value="600"/);
  assert.match(html, /Damage observed at return<\/textarea>/);
});

test('disputed returns stop presenting clean-return decisions despite the physical status', () => {
  const request = { handover_status: 'return_photos_uploaded' };
  assert.equal(returnReviewState(request, {}).awaitingDecision, true);
  for (const [rental, booking] of [
    [{ ...request, disputed_at: '2026-11-11' }, {}],
    [request, { dispute: { status: 'raised' } }],
    [request, { deposit_state: 'frozen' }],
  ]) {
    const state = returnReviewState(rental, booking);
    assert.equal(state.awaitingDecision, false);
    assert.match(state.label, /condition disputed; independent human review/);
  }
});

test('FastAPI validation arrays and permission errors become readable text', () => {
  const error = {
    response: {
      data: {
        detail: [
          { loc: ['body', 'reason'], msg: 'String should have at least 1 character' },
          { loc: ['body', 'inspection_id'], msg: 'Input should be a valid UUID' },
        ],
      },
    },
  };
  assert.equal(typeof apiErrorMessage(error), 'string');
  assert.match(apiErrorMessage(error), /reason: String should/);
  assert.match(apiErrorMessage(error), /inspection_id: Input should/);
  assert.equal(
    apiErrorMessage({ response: { data: { detail: 'Not authorized for this booking' } } }),
    'Not authorized for this booking',
  );
});

test('reviewed return retains clean-return gating and shows the recorded review', () => {
  const state = returnReviewState(
    { handover_status: 'return_photos_uploaded', disputed_at: '2026-11-11' },
    { dispute: { status: 'settled_arbitrated' }, deposit_state: 'settled' },
  );
  assert.equal(state.awaitingDecision, false);
  assert.equal(state.reviewed, true);
  assert.match(state.label, /Return reviewed/);
  assert.doesNotMatch(state.label, /review pending/);
});

test('accepted claim response awaits administrator review without asking for another borrower response', () => {
  const html = renderToStaticMarkup(
    React.createElement(DisputeResolutionModal, {
      booking: {
        ...base,
        dispute: {
          status: 'raised',
          claim_version: 3,
          claimed_deduction_paise: 60000,
          borrower_accepted: true,
        },
      },
      user: { id: 'borrower' },
      api: {},
      onChange() {},
      returnReady: true,
    }),
  );
  assert.match(html, /Borrower agreement recorded; awaiting independent human review/);
  assert.doesNotMatch(html, /Awaiting borrower response and independent human review/);
  assert.doesNotMatch(html, /Authorize mutually agreed settlement/);
});
