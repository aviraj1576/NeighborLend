export function toPaise(value) {
  if (!/^\d{1,8}(\.\d{1,2})?$/.test(String(value)))
    throw new Error('Enter rupees with at most two decimals.');
  const [whole, fraction = ''] = String(value).split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
}

export const rupees = (value) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value / 100);

let checkoutLoading = null;

export function loadCheckout() {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  if (checkoutLoading) return checkoutLoading;
  checkoutLoading = new Promise((resolve, reject) => {
    let script = document.querySelector('[data-neighborlend-checkout]');
    const created = !script;
    if (!script) {
      script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.dataset.neighborlendCheckout = 'true';
    }
    const finish = (error) => {
      clearTimeout(timer);
      script.onload = null;
      script.onerror = null;
      if (error) {
        script.remove();
        reject(error);
      } else resolve(window.Razorpay);
    };
    const timer = setTimeout(
      () => finish(new Error('Razorpay checkout timed out. Retry when available.')),
      15000,
    );
    script.onload = () => finish(window.Razorpay ? null : new Error('Razorpay unavailable.'));
    script.onerror = () => finish(new Error('Razorpay unavailable. No payment was verified.'));
    if (created) document.head.appendChild(script);
  }).finally(() => {
    checkoutLoading = null;
  });
  return checkoutLoading;
}

const pendingCheckouts = new WeakMap();

export function checkout(api, bookingId, loader = loadCheckout) {
  let pending = pendingCheckouts.get(api);
  if (!pending) {
    pending = new Map();
    pendingCheckouts.set(api, pending);
  }
  if (pending.has(bookingId)) return pending.get(bookingId);
  const operation = runCheckout(api, bookingId, loader).finally(() => pending.delete(bookingId));
  pending.set(bookingId, operation);
  return operation;
}

async function runCheckout(api, bookingId, loader) {
  const { data: order } = await api.post('/payments/create-order', { booking_id: bookingId });
  if (order.sandbox_only !== true || order.test_mode !== true)
    throw new Error('Backend sandbox-only confirmation is required. Checkout is blocked.');
  if (order.booking_id !== bookingId)
    throw new Error('Checkout order does not match this booking.');
  if (
    order.currency !== 'INR' ||
    !Number.isSafeInteger(order.amount_paise) ||
    order.amount_paise <= 0 ||
    order.amount_paise > 1000000000
  )
    throw new Error('Invalid test order amount or currency. Refresh payment status.');
  if (order.provider === 'mock') {
    if (order.key_id || !/^order_mock_[A-Za-z0-9-]+$/.test(order.order_id || ''))
      throw new Error('Invalid local simulator order.');
    return { mock: true, order };
  }
  if (order.provider !== 'razorpay_test' || !/^rzp_test_[A-Za-z0-9]+$/.test(order.key_id || ''))
    throw new Error('Only Razorpay TEST mode is supported.');
  if (!/^order_[A-Za-z0-9]+$/.test(order.order_id || ''))
    throw new Error('Invalid Razorpay Test order.');
  const Razorpay = await loader();
  return new Promise((resolve, reject) => {
    let finished = false;
    let verifying = false;
    const dismiss = (message) => {
      if (!finished && !verifying) {
        finished = true;
        reject(new Error(message));
      }
    };
    const widget = new Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount_paise,
      currency: order.currency,
      name: 'NeighborLend — TEST MODE',
      description: 'Test rental + refundable deposit. Simulated accounting.',
      handler: async (result) => {
        if (finished || verifying) return;
        verifying = true;
        try {
          if (
            result.razorpay_order_id !== order.order_id ||
            !/^pay_[A-Za-z0-9]+$/.test(result.razorpay_payment_id || '') ||
            !/^[a-f0-9]{64}$/.test(result.razorpay_signature || '')
          )
            throw new Error('Invalid checkout result. Refresh verified payment status.');
          const response = await api.post('/payments/verify', {
            booking_id: bookingId,
            order_id: result.razorpay_order_id,
            payment_id: result.razorpay_payment_id,
            signature: result.razorpay_signature,
          });
          finished = true;
          resolve({ mock: false, booking: response.data });
        } catch (error) {
          finished = true;
          reject(error);
        }
      },
      modal: { ondismiss: () => dismiss('Checkout dismissed. Verify status before retrying.') },
    });
    widget.on('payment.failed', () => dismiss('Test payment failed. You can retry.'));
    widget.open();
  });
}

export function paymentLabel(booking) {
  if (booking.legacy) return 'Legacy rental — payment review required';
  if (booking.refund && booking.refund.status !== 'processed')
    return `Refund ${booking.refund.status}`;
  if (booking.booking_status === 'completed') return 'Settlement completed';
  if (booking.booking_status === 'cancelled') return 'Booking cancelled';
  if (booking.deposit_state === 'frozen') return 'Dispute pending — deposit frozen';
  if (booking.payment_status === 'failed')
    return 'Payment failed — handover locked; retry or reconcile';
  if (booking.payment_status === 'authorized')
    return 'Payment authorized — awaiting capture; handover locked';
  if (booking.payment_status !== 'captured') return 'Payment pending — handover locked';
  return 'Payment captured — deposit held';
}

export async function uploadRentalEvidence(api, bookingId, file, stage) {
  if (!bookingId) throw new Error('Load the verified booking before uploading evidence.');
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post(`/payments/bookings/${bookingId}/evidence?stage=${stage}`, form);
  return data.url;
}

export function paymentPermissions(booking, user, request) {
  const borrower = user?.id === booking.borrower_id;
  const participant = borrower || user?.id === booking.lender_id;
  const enabled =
    booking.operations_enabled === true &&
    booking.sandbox_only === true &&
    booking.test_mode === true &&
    ['mock', 'razorpay_test'].includes(booking.provider);
  return {
    checkout: enabled && borrower && booking.booking_status === 'awaiting_payment',
    reconcile:
      enabled &&
      borrower &&
      booking.provider === 'razorpay_test' &&
      booking.payment_status !== 'captured',
    cancel:
      participant &&
      ['pending', 'photos_uploaded'].includes(request.handover_status) &&
      ['awaiting_payment', 'funded'].includes(booking.booking_status),
    refund:
      enabled &&
      (participant || user?.is_admin) &&
      Boolean(booking.refund) &&
      booking.refund.status !== 'processed',
  };
}

export function apiErrorMessage(
  error,
  fallback = 'Request failed. Refresh status before retrying.',
) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail))
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc)
          ? item.loc.filter((value) => value !== 'body').join('.')
          : '';
        return `${field ? `${field}: ` : ''}${typeof item?.msg === 'string' ? item.msg : 'Invalid value'}`;
      })
      .join('; ');
  return error?.message || fallback;
}

export function returnReviewState(request, booking) {
  const disputed = Boolean(
    request?.disputed_at || booking?.dispute || booking?.deposit_state === 'frozen',
  );
  const reviewed = ['settled_arbitrated', 'settled_mutual'].includes(booking?.dispute?.status);
  return {
    disputed,
    reviewed,
    awaitingDecision:
      request?.handover_status === 'return_photos_uploaded' && !disputed && !booking?.refund,
    label:
      disputed && ['return_photos_uploaded', 'return_confirmed'].includes(request?.handover_status)
        ? reviewed
          ? 'Return reviewed — follow authorized settlement status'
          : 'Return reported — condition disputed; independent human review pending'
        : null,
  };
}
