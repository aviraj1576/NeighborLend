// localStorage is shared by all tabs in one browser profile. Reload account
// scoped state when another tab signs in or out, before it can submit stale UI.
export function watchSessionChanges(browser, onChange) {
  const changed = (event) => {
    if (event.storageArea !== browser.localStorage) return;
    if (event.key !== null && event.key !== 'nl_token') return;
    if (event.key === 'nl_token' && event.oldValue === event.newValue) return;
    onChange();
  };
  browser.addEventListener('storage', changed);
  return () => browser.removeEventListener('storage', changed);
}

// An expired request from a previous account must not clear a newer login.
export function invalidateSession(browser, requestToken) {
  if (!requestToken || browser.localStorage.getItem('nl_token') !== requestToken) return false;
  browser.localStorage.removeItem('nl_token');
  browser.dispatchEvent(new Event('auth:invalidated'));
  return true;
}
