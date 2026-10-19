// Run with: node --test "tests/js/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const R = require("../../frontpart/deepseek_/chat-render.js");

test("escapeHtml neutralises markup and quotes", () => {
  assert.equal(R.escapeHtml(`<img src=x onerror="alert('x')">&`), "&lt;img src=x onerror=&quot;alert(&#39;x&#39;)&quot;&gt;&amp;");
  assert.equal(R.escapeHtml(null), "");
});

test("renderModelText escapes model output so it cannot inject HTML", () => {
  const html = R.renderModelText('<script>alert(1)</script><b>hi</b>');
  assert.ok(!html.includes("<script"));
  assert.ok(!html.includes("<b>"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("renderModelText styles closed <think> blocks", () => {
  assert.equal(
    R.renderModelText("<think>plan</think>answer"),
    '<span class="think-text">plan</span>answer'
  );
});

test("renderModelText styles an unterminated <think> block while streaming", () => {
  assert.equal(R.renderModelText("<think>still thinking"), '<span class="think-text">still thinking</span>');
});

test("think tags split across stream chunks render correctly once accumulated", () => {
  let text = "";
  for (const piece of ["<thi", "nk>ab", "c</th", "ink>done"]) text += piece;
  assert.equal(R.renderModelText(text), '<span class="think-text">abc</span>done');
});

test("think content cannot smuggle markup either", () => {
  const html = R.renderModelText("<think><img src=x onerror=1></think>");
  assert.ok(!html.includes("<img"));
});

test("line splitter keeps partial lines until they are complete", () => {
  const s = R.createLineSplitter();
  assert.deepEqual(s.push('{"a":1}\n{"b"'), ['{"a":1}']);
  assert.deepEqual(s.push(':2}\n\n'), ['{"b":2}']);
  assert.deepEqual(s.push("tail"), []);
  assert.deepEqual(s.flush(), ["tail"]);
  assert.deepEqual(s.flush(), []);
});

test("parseStreamLine returns objects only", () => {
  assert.deepEqual(R.parseStreamLine('{"done":true}'), { done: true });
  assert.equal(R.parseStreamLine("not json"), null);
  assert.equal(R.parseStreamLine("42"), null);
  assert.equal(R.parseStreamLine("null"), null);
});

test("imagesFromField handles comma strings, arrays, empties and junk", () => {
  assert.deepEqual(R.imagesFromField("QUJD,REVG"), ["QUJD", "REVG"]);
  assert.deepEqual(R.imagesFromField(["QUJD"]), ["QUJD"]);
  assert.deepEqual(R.imagesFromField(null), []);
  assert.deepEqual(R.imagesFromField(""), []);
  assert.deepEqual(R.imagesFromField('QUJD,"><script>,REVG'), ["QUJD", "REVG"]);
});

test("data URIs use the MIME type implied by the base64 header", () => {
  assert.ok(R.dataUri("iVBORw0KGgo=").startsWith("data:image/png;base64,"));
  assert.ok(R.dataUri("/9j/4AAQ").startsWith("data:image/jpeg;base64,"));
  assert.ok(R.dataUri("R0lGODlh").startsWith("data:image/gif;base64,"));
  assert.ok(R.dataUri("UklGRiQA").startsWith("data:image/webp;base64,"));
  assert.ok(R.dataUri("AAAA").startsWith("data:image/png;base64,"));
});

test("shortTitle truncates and falls back for image-only messages", () => {
  assert.equal(R.shortTitle("  hello \n world  ", 40), "hello world");
  assert.equal(R.shortTitle("x".repeat(100), 10), "xxxxxxxxx…");
  assert.equal(R.shortTitle("", 40), "Image chat");
});

test("cleanTitle strips think blocks, quotes and extra whitespace", () => {
  assert.equal(R.cleanTitle('<think>hmm</think>\n"Cats and dogs"\n', 60), "Cats and dogs");
  assert.equal(R.cleanTitle("<think>never closed", 60), "");
  assert.equal(R.cleanTitle("a ".repeat(50), 10).length, 10);
});
