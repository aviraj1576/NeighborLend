// Use the installed Vite transformer for the teammate's JSX UI primitives.
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
export async function load(url, context, nextLoad) {
  if (url.endsWith('.jsx') && url.includes('/src/components/')) {
    let source = await readFile(new URL(url), 'utf8');
    if (url.includes('/components/ui/')) {
      const { transformWithOxc } = await import('vite');
      source = (await transformWithOxc(source, fileURLToPath(url))).code;
    }
    return { format: 'module', source, shortCircuit: true };
  }
  return nextLoad(url, context);
}
