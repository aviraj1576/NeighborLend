import React, { useState } from 'react';
import { rupees } from './paymentFlow.js';

const h = React.createElement;

export default function RefundPanel({
  booking,
  user,
  busy,
  allowed,
  onAction,
  demoOutcome,
  onDemoOutcome,
}) {
  const [approved, setApproved] = useState(false);
  const refund = booking.refund;
  const canOperate = allowed && !booking.gateway_review && user?.is_admin === true;
  if (!refund)
    return h(
      'p',
      { role: 'status' },
      booking.deposit_state === 'frozen'
        ? 'Deposit frozen for independent human review. No deduction or refund is authorized.'
        : 'Deposit refund becomes eligible after confirmed return, or an authorized cancellation.',
    );
  const gateway = booking.provider === 'razorpay_test';
  const labels = {
    created: gateway
      ? 'Authorized — not yet sent to Razorpay; awaiting dispatch approval'
      : 'Authorized — awaiting simulated settlement',
    dispatching: 'Request in progress',
    unknown: 'Outcome unknown — reconcile before retry',
    pending: 'Pending provider confirmation',
    processed: 'Processed — confirmed settlement',
    failed: 'Failed — funds remain reserved',
  };
  const execute = () =>
    onAction('/payments/refunds/execute', { gateway_refund_approved: approved });
  return h(
    'section',
    { className: 'refund-panel', 'aria-label': 'Deposit refund', 'aria-busy': busy },
    h('h3', null, 'Refund & settlement'),
    h('p', { role: 'status' }, labels[refund.status] || 'Reconciliation required'),
    gateway &&
      refund.status === 'pending' &&
      h(
        'p',
        { role: 'status' },
        'Razorpay has accepted this Test refund but has not confirmed completion. Do not send another refund. An administrator can reconcile the saved refund status. Test Mode does not credit a real bank account.',
      ),
    gateway &&
      refund.provider_refund_id &&
      h('p', null, 'Razorpay refund reference: ', h('code', null, refund.provider_refund_id)),
    gateway &&
      refund.status === 'created' &&
      h(
        'p',
        null,
        'Confirming a clean return authorizes this amount. Sending it to Razorpay requires the separate approval below. Refresh checks the saved status without sending a refund.',
      ),
    h(
      'dl',
      null,
      ...[
        ['Authorized refund to borrower', refund.amount_paise],
        ['Human-approved damage deduction', refund.deduction_paise],
        ['Agreed rental allocation', refund.kind === 'cancellation' ? 0 : booking.rental_fee_paise],
        [
          'Simulated lender allocation',
          refund.kind === 'cancellation' ? 0 : booking.rental_fee_paise + refund.deduction_paise,
        ],
      ].map(([label, value]) =>
        h('div', { key: label }, h('dt', null, label), h('dd', null, rupees(value))),
      ),
    ),
    refund.kind === 'cancellation' &&
      h(
        'p',
        null,
        'Cancellation refund includes rental fee and deposit under the existing pre-receipt policy.',
      ),
    refund.error_code &&
      h(
        'p',
        { role: 'alert' },
        `Reconciliation notice: ${refund.error_code}. No refund success is recorded without provider confirmation.`,
      ),
    refund.status !== 'processed' &&
      !user?.is_admin &&
      h(
        'p',
        { role: 'status' },
        'Only an administrator can send or reconcile this refund. You can view its status here.',
      ),
    refund.status !== 'processed' &&
      canOperate &&
      h(
        'div',
        null,
        !gateway &&
          h(
            'label',
            null,
            'Demo refund outcome',
            h(
              'select',
              { value: demoOutcome, onChange: (e) => onDemoOutcome(e.target.value) },
              ...['processed', 'pending', 'failed'].map((value) =>
                h('option', { key: value, value }, value),
              ),
            ),
          ),
        h(
          'button',
          {
            type: 'button',
            disabled: busy || (gateway && refund.status === 'created'),
            onClick: () => onAction('/payments/refunds/reconcile', { demo_outcome: demoOutcome }),
          },
          gateway
            ? 'Reconcile refund status (no new refund)'
            : 'Simulate / reconcile authorized refund',
        ),
        gateway &&
          ['created', 'unknown', 'failed'].includes(refund.status) &&
          h(
            'div',
            null,
            h(
              'label',
              { className: 'refund-approval' },
              h('input', {
                type: 'checkbox',
                disabled: busy,
                checked: approved,
                onChange: (e) => setApproved(e.target.checked),
              }),
              `I approve a Razorpay Test refund of ${rupees(refund.amount_paise)}. No real money.`,
            ),
            refund.status !== 'failed' &&
              h(
                'button',
                { type: 'button', disabled: busy || !approved, onClick: execute },
                refund.status === 'unknown'
                  ? 'Retry same approved Test refund'
                  : 'Send approved Test refund',
              ),
            refund.status === 'failed' &&
              user?.is_admin &&
              h(
                'button',
                {
                  type: 'button',
                  disabled: busy || !approved,
                  onClick: () =>
                    onAction('/payments/refunds/execute', {
                      gateway_refund_approved: approved,
                      retry_failed: true,
                    }),
                },
                'Administrator: retry confirmed failed Test refund',
              ),
            refund.status === 'failed' &&
              !user?.is_admin &&
              h(
                'p',
                null,
                'An administrator must authorize a new attempt after confirmed gateway failure.',
              ),
          ),
      ),
    h('p', null, 'Lender allocation is simulated accounting only. No lender payout is sent.'),
  );
}
