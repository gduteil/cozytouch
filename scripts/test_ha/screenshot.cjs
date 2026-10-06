// A screenshot of the test Home Assistant, logged in as its owner.
//
//   NODE_PATH=$(npm root -g) node scripts/test_ha/screenshot.cjs PATH OUT.png \
//       [--click TEXT]... [--width 430] [--height 1100] [--full]
//
// PATH is a frontend path ("/config/devices/device/<id>", "/lovelace/0").
// Each --click clicks the first element showing that exact text, in order,
// which is how a more-info dialog is opened : click the entity's name on its
// device page. Playwright's text locators pierce the frontend's shadow DOM.
// --full captures the whole page rather than the viewport ; leave it off
// when a dialog is open, since the dialog is pinned to the viewport.
//
// The frontend reads its session from localStorage, so the owner's tokens
// (written by run.py into TEST_HA_DIR) are put there before the page loads.

const { existsSync, readFileSync } = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const WORK = process.env.TEST_HA_DIR || path.join(ROOT, ".test-ha");
const INSTANCE = path.join(WORK, "instance.json");
const SAVED = existsSync(INSTANCE) ? JSON.parse(readFileSync(INSTANCE, "utf8")) : {};
const BASE = `http://127.0.0.1:${process.env.TEST_HA_PORT || SAVED.ha_port || 8123}`;

function parse(argv) {
  const options = { clicks: [], width: 430, height: 1100, full: false };
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--click") options.clicks.push(argv[++i]);
    else if (arg === "--width") options.width = Number(argv[++i]);
    else if (arg === "--height") options.height = Number(argv[++i]);
    else if (arg === "--full") options.full = true;
    else positional.push(arg);
  }
  [options.page = "/", options.out = "screenshot.png"] = positional;
  return options;
}

(async () => {
  const options = parse(process.argv.slice(2));
  const tokens = JSON.parse(readFileSync(path.join(WORK, "tokens.json"), "utf8"));

  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM || undefined,
  });
  const page = await browser.newPage({
    viewport: { width: options.width, height: options.height },
    locale: "fr-FR",
    timezoneId: "Europe/Paris",
  });

  await page.addInitScript(
    ({ tokens, base }) => {
      localStorage.setItem(
        "hassTokens",
        JSON.stringify({
          ...tokens,
          hassUrl: base,
          clientId: base + "/",
          expires: Date.now() + tokens.expires_in * 1000,
        })
      );
    },
    { tokens, base: BASE }
  );

  await page.goto(BASE + options.page, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);

  for (const text of options.clicks) {
    await page.getByText(text, { exact: true }).first().click();
    await page.waitForTimeout(1500);
  }

  await page.screenshot({ path: options.out, fullPage: options.full });
  await browser.close();
})().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
