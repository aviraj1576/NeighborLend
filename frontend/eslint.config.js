export default [{
  files: ['src/components/**/*.{js,jsx}', 'src/context/*.{js,jsx}', 'src/api/*.js', 'src/pages/{BorrowRequestDetail,Chat,ListingDetail}.jsx', 'src/App.jsx'],
  languageOptions: { ecmaVersion: 2022, sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
  rules: {
    'constructor-super': 'error', 'no-async-promise-executor': 'error',
    'no-constant-condition': 'error', 'no-dupe-args': 'error', 'no-dupe-keys': 'error',
    'no-duplicate-case': 'error', 'no-ex-assign': 'error', 'no-func-assign': 'error',
    'no-unexpected-multiline': 'error', 'no-unreachable': 'error', 'valid-typeof': 'error',
  },
}];
