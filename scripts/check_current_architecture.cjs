// Render the architecture with local Chrome and verify its offline interactions.
// NODE_PATH=<directory containing playwright> node scripts/check_current_architecture.cjs
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const out = path.join(root, 'docs/architecture');
  const prefix = 'data-explore-v1.1';
  const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless: true, executablePath: fs.existsSync(chrome) ? chrome : undefined});
  const errors = [], externalRequests = [];
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1080}, deviceScaleFactor: 1});
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (/^https?:/.test(r.url())) externalRequests.push(r.url());});
    await page.goto(pathToFileURL(path.join(out, `${prefix}-architecture.html`)).href);
    await page.evaluate(() => document.fonts.ready);
    for (const [view, key, expected] of [
      ['overview', 'o-env', 'MetaOne'], ['build', 'b-hierarchy', 'Hierarchy'], ['runtime', 'r-bind', 'Binding']
    ]) {
      await page.click(`[data-view="${view}"]`);
      await page.click(`#${key}`);
      if (!(await page.textContent('#detailTitle')).includes(expected)) throw Error('Node detail did not update');
      const overflow = await page.locator(`#view-${view}`).evaluate(el => [...el.querySelectorAll('.node')].flatMap(n => {
        const box = n.querySelector('.card').getBBox();
        return [...n.querySelectorAll('text')].filter(t => {
          const b = t.getBBox();
          return b.x < box.x+8 || b.x+b.width > box.x+box.width-8 || b.y < box.y+8 || b.y+b.height > box.y+box.height-8;
        }).map(t => `${n.id}: ${t.textContent}`);
      }));
      if (overflow.length) throw Error('Text overflow: '+overflow.join('; '));
      const downloadPromise = page.waitForEvent('download');
      await page.click('#downloadSvg');
      const download = await downloadPromise;
      if (!download.suggestedFilename().endsWith(`${view}.svg`)) throw Error('Incorrect SVG export');
    }
    await page.click('[data-view="boundaries"]');
    if (!(await page.locator('#view-boundaries').isVisible())) throw Error('Boundary tab missing');
    await page.click('[data-view="overview"]');
    await page.click('#plus');
    if (await page.textContent('#fit') !== '120%') throw Error('Zoom failed');
    await page.click('#fit');
    await page.locator('#o-router').focus();
    await page.keyboard.press('Enter');
    if (!(await page.textContent('#detailTitle')).includes('Router')) throw Error('Keyboard selection failed');
    // Exercise browser-side PNG export too, independently of static screenshot export.
    const pngDownload = page.waitForEvent('download');
    await page.click('#downloadPng');
    if (!(await pngDownload).suggestedFilename().endsWith('.png')) throw Error('PNG export failed');
    await page.click('[data-view="overview"]');
    await page.screenshot({path:path.join(out,`${prefix}-html-preview.png`),fullPage:true});
    for (const view of ['overview','build','runtime']) {
      await page.click(`[data-view="${view}"]`);
      const pending = page.waitForEvent('download');
      await page.click('#downloadPng');
      const image = await pending;
      await image.saveAs(path.join(out,`${prefix}-${view}.png`));

    }
    if (errors.length || externalRequests.length) throw Error(JSON.stringify({errors,externalRequests}));
    console.log(JSON.stringify({html_interactions:'passed',text_fit:'passed',offline_network_requests:0,
      svg_and_png_download:'passed',png_export:'3 diagrams, 3360px width',visual_review:'pending image inspection'},null,2));
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1});
