import React from 'react';
import { rupees } from './paymentFlow.js';

const h = React.createElement;
const timestamp = (value) =>
  value
    ? new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('en-IN')
    : 'Time unavailable';

export default function FinancialTimeline({ booking }) {
  const journals = (booking.journal || []).reduce(
    (groups, row) => groups.set(row.journal_id, [...(groups.get(row.journal_id) || []), row]),
    new Map(),
  );
  return h(
    'details',
    { className: 'financial-timeline' },
    h('summary', null, 'Transaction timeline & balanced journal'),
    !booking.transactions?.length && h('p', null, 'No financial transactions recorded.'),
    ...(booking.transactions || []).map((row) =>
      h(
        'p',
        { key: row.id },
        `${timestamp(row.created_at)} · ${row.type}: ${rupees(row.amount_paise)} — ${row.status}`,
      ),
    ),
    ...Array.from(journals, ([id, lines]) => {
      const debit = lines
        .filter((row) => row.side === 'DEBIT')
        .reduce((sum, row) => sum + row.amount_paise, 0);
      const credit = lines
        .filter((row) => row.side === 'CREDIT')
        .reduce((sum, row) => sum + row.amount_paise, 0);
      const balanced = debit === credit && debit > 0;
      return h(
        'section',
        { key: id, 'aria-label': 'Simulated journal' },
        h('p', null, `Journal ${id}`),
        ...lines.map((row, index) =>
          h('p', { key: index }, `${row.side} ${row.account}: ${rupees(row.amount_paise)}`),
        ),
        h(
          'p',
          { role: balanced ? 'status' : 'alert' },
          `Debits ${rupees(debit)} · Credits ${rupees(credit)} · ${balanced ? 'Balanced' : 'Review required'}`,
        ),
      );
    }),
    h('h3', null, 'Audit history'),
    ...(booking.audit || []).map((row) =>
      h(
        'p',
        { key: row.id },
        `${timestamp(row.created_at)} · ${row.action.replaceAll('_', ' ')}: ${row.details.reason || row.details.provider_status || ''}`,
      ),
    ),
  );
}
