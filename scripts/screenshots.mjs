// Captures desktop + mobile screenshots of the main pages for the README.
//
//   node scripts/screenshots.mjs [baseUrl] [outDir]
//
// Needs the Flask server running (it serves the site and the chat API) and a Chromium that
// Playwright can launch. Set CHROMIUM_PATH to use an existing browser build instead of
// the one Playwright downloads with `npx playwright install chromium`.
// CHAT_MODEL / CHAT_PROMPT choose the model and prompt used for the chat screenshot.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const base = (process.argv[2] || "http://127.0.0.1:5000").replace(/\/$/, "");
const outDir = process.argv[3] || "docs/screenshots";
const prompt = process.env.CHAT_PROMPT || "Explain what a hash map is in two sentences.";
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});

const profiles = {
  desktop: { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};

const pages = [
  { name: "home", url: "/", fullPage: true },
  { name: "projects", url: "/projects/", fullPage: true },
];

for (const [profileName, profile] of Object.entries(profiles)) {
  const context = await browser.newContext(profile);
  const page = await context.newPage();

  for (const p of pages) {
    await page.goto(base + p.url, { waitUntil: "networkidle" });
    await page.waitForTimeout(800); // let posters / media controls settle
    await page.screenshot({ path: path.join(outDir, `${p.name}-${profileName}.png`), fullPage: p.fullPage });
  }

  // Chat: start a session, send a message and wait for the streamed reply.
  await page.goto(base + "/deepseek_/", { waitUntil: "networkidle" });
  if (profileName === "mobile") await page.click("#toggleSidebar"); // sidebar starts collapsed on small screens
  await page.click("#newSession");
  if (process.env.CHAT_MODEL) await page.selectOption("#modelSelect", process.env.CHAT_MODEL);
  await page.fill("#userInput", prompt);
  await page.click("#sendButton");
  await page.waitForFunction(() => {
    const send = document.getElementById("sendButton");
    return !send.disabled && document.querySelectorAll("#chatbox .message.assistant").length > 0;
  }, null, { timeout: 120000 });
  // The first message also triggers a title request; wait (best effort) for it to replace "New Chat".
  await page
    .waitForFunction(() => document.querySelector(".session-container .session-name")?.textContent !== "New Chat", null, {
      timeout: 90000,
    })
    .catch(() => {});
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, `chat-${profileName}.png`) });

  await context.close();
}
await browser.close();
console.log("screenshots written to", outDir);
