// Prueba de extremo a extremo, en Chrome real, del campo «Credencial de Composio» y de las pestañas viejas.
// Uso: node tests/e2e/llave.mjs <url> <archivo-contraseña> <archivo-.env-esperado> <carpeta-capturas> <modo>
//   modo "rechazo": llave falsa contra el Composio que tenga configurado el servidor → no se guarda nada.
//   modo "guardado": llave de prueba (LLAVE_OK) contra el Composio simulado → se guarda y la interfaz cambia.
//   modo "pestana-vieja": carga la interfaz ANTERIOR (APP_VIEJO) contra el servidor actual → debe pedir recargar.
//   modo "recarga": con la interfaz actual abierta, cambia la huella (touch) → la página se recarga sola.
import { chromium } from 'playwright-core';
import { readFileSync, existsSync, statSync, utimesSync } from 'node:fs';

const [url, passwordFile, envFile, out, mode] = process.argv.slice(2);
const password = readFileSync(passwordFile, 'utf8').trim();
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1480, height: 1000 }, deviceScaleFactor: 2, locale: 'es-MX' });
const page = await context.newPage();
const results = [];
const check = (name, ok, detail = '') => { results.push(ok); console.log(`${ok ? 'OK   ' : 'FALLA'} ${name}${detail ? ' — ' + detail : ''}`); };
const toastText = async () => (await page.locator('#toast:not([hidden])').textContent({ timeout: 60000 })).trim();

if (mode === 'pestana-vieja') {
  const old = readFileSync(process.env.APP_VIEJO, 'utf8');
  await page.route('**/app.js', route => route.fulfill({ contentType: 'application/javascript', body: old }));
}
await page.goto(url);
await page.fill('#password', password);
await page.click('#auth-form button[type=submit]');
await page.waitForSelector('.bot-row');
await page.click('.bot-row >> nth=0');

if (mode === 'pestana-vieja') {
  await page.click('#tab-connections');
  await page.waitForTimeout(4500);
  const heading = (await page.locator('#panel .panel-heading h3').textContent()).trim();
  check('la interfaz anterior es la que ve Joe', heading.startsWith('Conexiones de'), heading);
  check('la interfaz anterior no tiene el campo', (await page.locator('#key-form').count()) === 0);
  const banner = (await page.locator('#status-banner').textContent()).trim();
  check('el servidor le avisa que recargue', /Recarga la página/.test(banner), banner);
  await page.screenshot({ path: `${out}/llave-0-pestana-vieja-con-aviso.png` });
} else if (mode === 'recarga') {
  await page.waitForTimeout(1500);
  const before = await page.evaluate(() => performance.timeOrigin);
  const now = new Date();
  utimesSync(process.env.TOCAR, now, now);   // cambia la huella de la interfaz, como una actualización
  await page.waitForFunction(t => performance.timeOrigin !== t, before, { timeout: 20000 }).catch(() => {});
  const after = await page.evaluate(() => performance.timeOrigin);
  check('la pestaña se recargó sola tras la actualización', after !== before);
  await page.waitForSelector('#auth-form, .bot-row');
  check('sigue con sesión tras recargar (cookie)', (await page.locator('.bot-row').count()) > 0);
} else {
  await page.click('#tab-connections');
  await page.waitForSelector('#key-form');
  const first = await page.evaluate(() => document.querySelector('#panel').firstElementChild.nextElementSibling?.id
    || [...document.querySelectorAll('#panel > *')].findIndex(el => el.id === 'composio-key'));
  const box = await page.locator('#composio-key').boundingBox();
  const panel = await page.locator('#panel').boundingBox();
  check('pestaña Apps → sección «Credencial de Composio» visible sin desplazarse', box.y >= panel.y && box.y + box.height <= 1000, `posición ${Math.round(box.y)}px`);
  check('título de la sección', (await page.locator('#key-title').textContent()).trim() === 'Credencial de Composio');
  check('el campo oculta lo que se escribe', (await page.getAttribute('#key-input', 'type')) === 'password');
  if (mode === 'rechazo') {
    check('botón inicial', (await page.locator('#key-save').textContent()).trim() === 'Guardar solo en .env');
    await page.screenshot({ path: `${out}/llave-1-campo-en-apps.png` });
    await page.fill('#key-input', 'ck_llave_falsa_para_prueba_0000');
    await page.click('#key-save');
    const text = await toastText();
    check('llave falsa rechazada con mensaje claro', /NO se guardó/.test(text), text);
    check('no se escribió ningún archivo .env', !existsSync(envFile));
    await page.screenshot({ path: `${out}/llave-2-rechazo.png` });
  } else {
    await page.fill('#key-input', process.env.LLAVE_OK);
    await page.click('#key-save');
    const text = await toastText();
    check('aviso de guardado', /Llave guardada en \.env y verificada/.test(text), text);
    await page.waitForFunction(() => /Llave propia en \.env/.test(document.querySelector('.key-status')?.textContent || ''), null, { timeout: 30000 });
    check('estado cambia a «Llave propia en .env»', true, (await page.locator('.key-status').textContent()).trim());
    check('el botón pasa a «Reemplazar llave»', (await page.locator('#key-save').textContent()).trim() === 'Reemplazar llave');
    check('el campo queda vacío (no muestra la llave)', (await page.inputValue('#key-input')) === '');
    const saved = existsSync(envFile) ? readFileSync(envFile, 'utf8') : '';
    check('el archivo .env contiene la llave', saved.trim() === 'COMPOSIO_API_KEY=' + process.env.LLAVE_OK);
    check('permiso del archivo 600', existsSync(envFile) && (statSync(envFile).mode & 0o777) === 0o600);
    check('la llave no aparece en el HTML', !(await page.content()).includes(process.env.LLAVE_OK));
    check('las apps cargan con la llave', (await page.locator('.app-row').count()) === 6);
    await page.screenshot({ path: `${out}/llave-3-guardada.png` });
    await page.reload();
    await page.waitForSelector('.bot-row');
    await page.click('.bot-row >> nth=0');
    await page.click('#tab-connections');
    await page.waitForFunction(() => /Llave propia en \.env/.test(document.querySelector('.key-status')?.textContent || ''), null, { timeout: 30000 });
    check('tras recargar la página sigue «Llave propia en .env»', true);
  }
}
await browser.close();
console.log(results.every(Boolean) ? `RESULTADO: ${results.length}/${results.length} verificaciones pasan` : 'RESULTADO: HAY FALLAS');
process.exit(results.every(Boolean) ? 0 : 1);
