import React from 'react';

/**
 * Input — shared form control.
 *
 * Native input/select/textarea styled with the skill's base tokens (hairline border on
 * --line-strong, focus ring on --action, no grey-on-grey). Keeps the standard controlled
 * props so existing forms keep working: value, onChange, name, type, placeholder, disabled,
 * error, label, id, className, rows.
 */
export default function Input({
  id,
  label,
  name,
  type = 'text',
  value,
  defaultValue,
  onChange,
  placeholder = '',
  disabled = false,
  error,
  className = '',
  rows,
  ...rest
}) {
  const hasLabel = !!label;
  const inputCls = ['input', error ? 'input--error' : '', className].filter(Boolean).join(' ');
  const wrapperCls = ['input-wrap', error ? 'input-wrap--error' : ''].filter(Boolean).join(' ');
  const fieldId = id || name;
  const isSelect = type === 'select';
  const isTextarea = type === 'textarea';

  return (
    <div className={wrapperCls}>
      {hasLabel && (
        <label htmlFor={fieldId} className="input-label">
          {label}
        </label>
      )}
      {isSelect ? (
        <select
          id={fieldId}
          name={name}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          disabled={disabled}
          className={inputCls}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          {...rest}
        >
          {children}
        </select>
      ) : isTextarea ? (
        <textarea
          id={fieldId}
          name={name}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          className={inputCls}
          rows={rows || 4}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          {...rest}
        />
      ) : (
        <input
          id={fieldId}
          name={name}
          type={type}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          className={inputCls}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          {...rest}
        />
      )}
      {error && fieldId && (
        <p id={`${fieldId}-error`} className="input-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

Input.displayName = 'Input';
