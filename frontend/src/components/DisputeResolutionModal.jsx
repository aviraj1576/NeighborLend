import React, { useRef, useState } from 'react';
import { apiErrorMessage, rupees, toPaise } from './paymentFlow.js';

const h = React.createElement;

export default function DisputeResolutionModal({
  booking,
  user,
  api,
  onChange,
  returnReady,
  request,
}) {
  const [amount, setAmount] = useState(() =>
    String((booking.dispute?.claimed_deduction_paise || 0) / 100),
  );
  const [notes, setNotes] = useState(() =>
    user?.id === booking.lender_id ? booking.dispute?.lender_claim_notes || '' : '',
  );
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [refreshWarning, setRefreshWarning] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [refs, setRefs] = useState(() =>
    Object.fromEntries(
      ['inspection_id', 'cv_run_id', 'assessment_id'].map((key) => [
        key,
        booking.dispute?.[key] || '',
      ]),
    ),
  );
  const claim = booking.dispute;
  const [reviewedVersion, setReviewedVersion] = useState(booking.dispute?.claim_version || 1);
  const reviewChanged = Boolean(claim && claim.claim_version !== reviewedVersion);
  const lender = user?.id === booking.lender_id;
  const borrower = user?.id === booking.borrower_id;
  const preReceipt =
    ['pending', 'photos_uploaded', 'issue_reported'].includes(request?.handover_status) &&
    !request?.handover_confirmed_at &&
    !request?.borrowing_started_at;
  const recoveryActions = claim
    ? preReceipt
      ? [['cancel', 'Item recovered: cancel and refund']]
      : [['return', 'Permit return photographs']]
    : [
        ['continue', 'Resume confirmation sequence'],
        ['return', 'Permit return photographs'],
        ['cancel', 'Item recovered: cancel and refund'],
      ];
  async function action(path, data) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    setSuccess('');
    setRefreshWarning('');
    try {
      const response = await api.post(
        path,
        path.startsWith('/borrow-requests/')
          ? data
          : {
              booking_id: booking.id,
              ...(path === '/disputes/respond' ? { claim_version: claim.claim_version } : {}),
              ...data,
            },
        { timeout: 20000 },
      );
      const isClaim = path === '/disputes/raise';
      setSuccess(
        isClaim
          ? `Claim saved: ${rupees(response.data.claimed_deduction_paise)} proposed deduction. Deposit remains frozen for independent human review.`
          : 'Decision recorded. Financial deductions still require independent administrator authorization.',
      );
      try {
        await onChange(isClaim ? { claim: response.data } : undefined);
      } catch {
        setRefreshWarning(
          'Saved successfully, but status refresh failed. Refresh payment status before submitting again.',
        );
      }
    } catch (err) {
      const message = apiErrorMessage(err, 'Submission could not be confirmed.');
      setError(
        err.response
          ? message
          : `${message} Refresh claim status before retrying; the submission may already be saved.`,
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return h(
    'section',
    { className: 'payment-dispute', 'aria-label': 'Human dispute review', 'aria-busy': busy },
    h('h3', null, 'Condition claim & human review'),
    h(
      'p',
      null,
      'AI evidence is advisory. No AI finding authorizes a deduction. Lender credits below are simulated, not payouts.',
    ),
    claim &&
      h(
        'div',
        null,
        h('p', null, `Claim: ${rupees(claim.claimed_deduction_paise)} — ${claim.status}`),
        h('p', null, claim.lender_claim_notes),
        h('p', null, `Borrower response: ${claim.borrower_response_notes || 'Not yet provided'}`),
        h(
          'p',
          null,
          `Approved deduction: ${claim.approved_deduction_paise == null ? 'Not authorized' : rupees(claim.approved_deduction_paise)}`,
        ),
        h(
          'p',
          null,
          `Proposed deposit remainder: ${rupees(booking.security_deposit_paise - claim.claimed_deduction_paise)}`,
        ),
        ...Object.keys(refs).map((key) =>
          h('p', { key }, `${key}: ${claim[key] || 'No linked inspection'}`),
        ),
        h(
          'p',
          null,
          'References are unverified pointers. No AI report is fabricated or fetched through this payment screen.',
        ),
      ),
    error && h('p', { role: 'alert', className: 'error-banner' }, error),
    success && h('p', { role: 'status', 'aria-live': 'polite' }, success),
    refreshWarning && h('p', { role: 'alert' }, refreshWarning),
    busy && h('p', { role: 'status' }, 'Saving decision…'),
    claim?.status === 'raised' &&
      h(
        'p',
        { role: 'status' },
        `Saved claim ${rupees(claim.claimed_deduction_paise)}, version ${claim.claim_version}. ${claim.borrower_accepted ? 'Borrower agreement recorded; awaiting independent human review' : 'Awaiting borrower response and independent human review'}; no deduction is approved.`,
      ),
    claim?.status === 'needs_claim' &&
      h(
        'p',
        { role: 'status' },
        'Return condition rejected. Submit the proposed deduction and description for human review.',
      ),
    ((lender &&
      returnReady &&
      !booking.refund &&
      (!claim || (!claim.borrower_accepted && ['raised', 'needs_claim'].includes(claim.status)))) ||
      (borrower && claim?.status === 'raised')) &&
      h(
        'div',
        null,
        h(
          'label',
          null,
          lender ? 'Claim description' : 'Response to claim',
          h('textarea', {
            value: notes,
            maxLength: 2000,
            onChange: (e) => setNotes(e.target.value),
          }),
        ),
        lender &&
          h(
            'label',
            null,
            'Requested deduction (₹)',
            h('input', {
              inputMode: 'decimal',
              value: amount,
              onChange: (e) => setAmount(e.target.value),
            }),
          ),
        lender &&
          h(
            'details',
            null,
            h('summary', null, 'Optional existing AI evidence references'),
            ...Object.keys(refs).map((key) =>
              h(
                'label',
                { key },
                key,
                h('input', {
                  value: refs[key],
                  onChange: (e) => setRefs({ ...refs, [key]: e.target.value }),
                }),
              ),
            ),
          ),
        lender &&
          h(
            'button',
            {
              disabled: busy || !notes.trim(),
              type: 'button',
              onClick: () => {
                try {
                  action('/disputes/raise', {
                    claimed_deduction_paise: toPaise(amount),
                    reason: notes,
                    ...Object.fromEntries(Object.entries(refs).filter(([, v]) => v)),
                  });
                } catch (err) {
                  setError(err.message);
                }
              },
            },
            busy ? 'Saving claim…' : 'Submit or revise human claim',
          ),
        borrower &&
          claim?.status === 'raised' &&
          h(
            'div',
            null,
            h(
              'button',
              {
                disabled: busy,
                type: 'button',
                onClick: () => action('/disputes/respond', { accepted: false, notes }),
              },
              'Disagree — keep deposit frozen',
            ),
            h(
              'button',
              {
                disabled: busy,
                type: 'button',
                onClick: () => action('/disputes/respond', { accepted: true, notes }),
              },
              'Agree to exact claimed amount',
            ),
          ),
      ),
    claim?.borrower_accepted &&
      claim.status === 'raised' &&
      h(
        'p',
        { role: 'status' },
        'Borrower response recorded. An independent human administrator must review evidence and authorize any deduction.',
      ),
    claim?.status === 'escalated' &&
      h(
        'p',
        { role: 'status' },
        'Claim rejected or escalated. Only a platform administrator can resolve these funds.',
      ),
    user?.is_admin &&
      !borrower &&
      !lender &&
      ['raised', 'needs_claim', 'escalated'].includes(claim?.status) &&
      h(
        'div',
        null,
        !returnReady &&
          h('p', { role: 'status' }, 'Physical return evidence is required before settlement.'),
        reviewChanged &&
          h(
            'div',
            null,
            h(
              'p',
              { role: 'alert' },
              'The claim changed. Review the updated evidence and enter a new decision reason.',
            ),
            h(
              'button',
              {
                type: 'button',
                disabled: busy,
                onClick: () => {
                  setReviewedVersion(claim.claim_version);
                  setAmount(String(claim.claimed_deduction_paise / 100));
                  setNotes('');
                },
              },
              'Review updated claim',
            ),
          ),
        h(
          'label',
          null,
          'Administrator resolution reason (required)',
          h('textarea', {
            value: notes,
            maxLength: 2000,
            onChange: (e) => setNotes(e.target.value),
          }),
        ),
        h(
          'label',
          null,
          'Administrator approved deduction (₹)',
          h('input', {
            value: amount,
            inputMode: 'decimal',
            onChange: (e) => setAmount(e.target.value),
          }),
        ),
        h(
          'button',
          {
            disabled: busy || !notes.trim() || !returnReady || reviewChanged,
            type: 'button',
            onClick: () => {
              try {
                action('/disputes/settle', {
                  approved_deduction_paise: toPaise(amount),
                  reason: notes,
                  claim_version: reviewedVersion,
                });
              } catch (err) {
                setError(err.message);
              }
            },
          },
          'Record administrator settlement decision',
        ),
        h(
          'button',
          {
            type: 'button',
            disabled: busy || !notes.trim() || !returnReady || reviewChanged,
            onClick: () =>
              action('/disputes/settle', {
                approved_deduction_paise: 0,
                reason: notes,
                claim_version: reviewedVersion,
              }),
          },
          'Reject damage claim (full deposit refund)',
        ),
      ),
    (borrower || lender) &&
      booking.payment_status === 'captured' &&
      !booking.refund &&
      !claim &&
      h(
        'div',
        null,
        h(
          'label',
          null,
          'Platform review request',
          h('textarea', {
            value: notes,
            maxLength: 2000,
            onChange: (e) => setNotes(e.target.value),
          }),
        ),
        h(
          'button',
          {
            disabled: busy || !notes.trim(),
            onClick: () =>
              action(`/borrow-requests/${booking.borrow_request_id}/dispute`, {
                description: notes,
              }),
          },
          'Request platform dispute review',
        ),
      ),
    user?.is_admin &&
      !borrower &&
      !lender &&
      (request?.handover_status === 'issue_reported' ||
        (claim &&
          ['pending', 'photos_uploaded', 'borrower_confirmed'].includes(
            request?.handover_status,
          ))) &&
      !booking.refund &&
      h(
        'div',
        null,
        h(
          'label',
          null,
          'Handover issue resolution reason',
          h('textarea', {
            value: notes,
            maxLength: 2000,
            onChange: (e) => setNotes(e.target.value),
          }),
        ),
        ...recoveryActions.map(([value, label]) =>
          h(
            'button',
            {
              key: value,
              disabled: busy || !notes.trim(),
              onClick: () =>
                action('/disputes/handover-issue/resolve', { action: value, reason: notes }),
            },
            label,
          ),
        ),
      ),
  );
}
