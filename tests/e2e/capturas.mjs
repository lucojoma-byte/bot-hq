// Revisión visual de JOE HQ con el Chrome instalado (playwright-core, sin descargar navegadores).
// Uso: node tests/e2e/capturas.mjs <url> <archivo-con-contraseña> <carpeta-salida>
// Abre una ventana limpia (equivalente a incógnito): primero debe pedir contraseña.
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';

const [url, passwordFile, out] = process.argv.slice(2);
const password = readFileSync(passwordFile, 'utf8').trim();
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1480, height: 900 }, deviceScaleFactor: 2, locale: 'es-MX' });
const page = await context.newPage();
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
const shot = name => page.screenshot({ path: `${out}/${name}.png` });
const steps = process.env.STEPS ? process.env.STEPS.split(',') : ['login', 'chat', 'apps', 'aprobar', 'computadora'];

await page.goto(url);
await page.waitForSelector('#auth-form');
if (steps.includes('login')) await shot('01-login-pide-contrasena');
await page.fill('#password', 'contraseña-incorrecta-123');
await page.click('#auth-form button[type=submit]');
await page.waitForSelector('#auth-error:not([hidden])');
console.log('contraseña incorrecta ->', await page.textContent('#auth-error'));
await page.fill('#password', password);
await page.click('#auth-form button[type=submit]');
await page.waitForSelector('.bot-row');
await page.waitForTimeout(1200);

const openBot = async name => { await page.click(`.bot-row:has-text("${name}")`); await page.waitForTimeout(1500); };
const tab = async key => { await page.click(`#tab-${key}`); await page.waitForTimeout(900); };

if (steps.includes('chat')) {
  await openBot(process.env.BOT_CHAT || 'Guardián Ventas');
  await shot('02-chat-mensajes-entre-bots');
  if (process.env.BOT_PEER) { await openBot(process.env.BOT_PEER); await shot('03-chat-companero'); }
}
if (steps.includes('apps')) {
  await openBot(process.env.BOT_APPS || 'Holding D7');
  await tab('connections');
  await page.waitForSelector('.app-row', { timeout: 60000 });
  // Se ocultan correos y usuarios de las cuentas para poder compartir la captura.
  // (La CSP de la app bloquea estilos en línea; se usa CSSOM, que sí está permitido.)
  await page.evaluate(() => document.querySelectorAll('.app-row .connection-sub').forEach(el => { el.style.filter = 'blur(4px)'; }));
  await page.waitForTimeout(400);
  await shot('04-apps-por-negocio');
}
if (steps.includes('aprobar')) {
  await openBot(process.env.BOT_APPS || 'Holding D7');
  await tab('approvals');
  await shot('05-aprobaciones');
}
if (steps.includes('computadora')) {
  await openBot(process.env.BOT_CHAT || 'Guardián Ventas');
  await page.waitForTimeout(2500);
  await shot(process.env.SHOT_COMPUTER || '06-computadora');
}
console.log('errores de consola:', errors.length ? errors : 'ninguno');
await browser.close();
