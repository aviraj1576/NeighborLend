import React, { useEffect, useState } from 'react';

export default function RentalEvidenceImage({ reference, api, ...props }) {
  const [source, setSource] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let objectUrl;
    setSource(null); setFailed(false);
    if (!/^\/api\/payments\/evidence\/[0-9a-f-]{36}$/.test(reference)) {
      setFailed(true);
      return undefined;
    }
    api.get(reference.slice(4), { responseType: 'blob' }).then(({ data }) => {
      if (active) { objectUrl = URL.createObjectURL(data); setSource(objectUrl); }
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [reference, api]);
  return source ? React.createElement('img', { ...props, src: source })
    : React.createElement('span', { role: 'status' }, failed ? 'Private evidence unavailable' : 'Loading private evidence…');
}
