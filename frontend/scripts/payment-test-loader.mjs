// Transform JSX modules through the same Oxc transform used by the Vite toolchain.
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
export async function load(url, context, nextLoad) {
  if (url.endsWith('.css') && url.includes('/src/')) {
    return { format: 'module', source: '', shortCircuit: true };
  }
  if (url.endsWith('.jsx') && url.includes('/src/components/')) {
    const { transformWithOxc } = await import('vite');
    const input = await readFile(new URL(url), 'utf8');
    const { code: source } = await transformWithOxc(input, fileURLToPath(url));
    return { format: 'module', source, shortCircuit: true };
  }
  return nextLoad(url, context);
}
