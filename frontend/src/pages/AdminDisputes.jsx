import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/client';
import Badge from '../components/ui/Badge';
import { apiError } from '../components/damage/damageApi';
import './Admin.css';

const FILTERS = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
];

export const AdminNav = ({ active }) => (
  <nav className="admin-tabs" aria-label="Admin sections">
    <Link className={active === 'disputes' ? 'admin-tab admin-tab--on' : 'admin-tab'} to="/admin/disputes">Disputes</Link>
    <Link className={active === 'support' ? 'admin-tab admin-tab--on' : 'admin-tab'} to="/admin/support">Support chats</Link>
  </nav>
);

const truncate = (text, n = 70) => (text && text.length > n ? `${text.slice(0, n)}…` : text);

export default function AdminDisputes() {
  const [status, setStatus] = useState('open');
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.get('/admin/disputes', { params: { status } });
      setRows(res.data);
      setError('');
    } catch (err) {
      setError(apiError(err, 'Could not load disputes.'));
    }
  }, [status]);

  useEffect(() => { setRows(null); load(); }, [load]);

  return (
    <div className="admin-page app-page">
      <div className="wrap">
        <section className="admin-card card">
          <h1 className="t-h1">Admin</h1>
          <AdminNav active="disputes" />
          <div className="admin-filter" role="group" aria-label="Filter disputes">
            {FILTERS.map((f) => (
              <button
                key={f.value} type="button"
                className={status === f.value ? 'admin-chip admin-chip--on' : 'admin-chip'}
                aria-pressed={status === f.value}
                onClick={() => setStatus(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {error && <div className="error-banner" role="alert">{error}</div>}
          {!rows && !error && <p className="t-body">Loading disputes…</p>}
          {rows && rows.length === 0 && <p className="t-body">No {status === 'all' ? '' : status} disputes.</p>}
          {rows && rows.length > 0 && (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th scope="col">Lend</th>
                    <th scope="col">Lender</th>
                    <th scope="col">Borrower</th>
                    <th scope="col">Reason</th>
                    <th scope="col">AI</th>
                    <th scope="col">Raised</th>
                    <th scope="col"><span className="sr-only">Open</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((d) => (
                    <tr key={d.id}>
                      <td>{d.title}{d.status === 'resolved' && <> <Badge variant="outline">{d.outcome}</Badge></>}</td>
                      <td>{d.lender?.name}</td>
                      <td>{d.borrower?.name}</td>
                      <td>{truncate(d.reason)}</td>
                      <td>{d.report_overall ? d.report_overall.replace('_', ' ') : '—'}</td>
                      <td>{new Date(d.created_at).toLocaleDateString()}</td>
                      <td><Link className="link" to={`/admin/disputes/${d.id}`}>Review</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
