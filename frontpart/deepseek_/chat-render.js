/*
 * Pure helpers for the chat page (no DOM access), so they can be unit-tested with
 * `node --test tests/js`. In the browser they are exposed as `window.ChatRender`.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ChatRender = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const BASE64_RE = /^[A-Za-z0-9+/]+={0,2}$/;

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Model output -> safe HTML. Everything is escaped first; only then are <think>...</think>
   * blocks (including one that is still open while streaming) wrapped in a styled span.
   */
  function renderModelText(text) {
    let html = escapeHtml(text);
    html = html.replace(/&lt;think&gt;([\s\S]*?)&lt;\/think&gt;/g, '<span class="think-text">$1</span>');
    html = html.replace(/&lt;think&gt;([\s\S]*)$/, '<span class="think-text">$1</span>');
    return html;
  }

  /** Splits a streamed NDJSON body into complete lines, keeping any partial line for the next chunk. */
  function createLineSplitter() {
    let buffer = "";
    return {
      push(chunk) {
        buffer += chunk;
        const lines = buffer.split("\n");
        buffer = lines.pop();
        return lines.map((l) => l.trim()).filter(Boolean);
      },
      flush() {
        const rest = buffer.trim();
        buffer = "";
        return rest ? [rest] : [];
      },
    };
  }

  /** Parses one NDJSON line; returns null for anything that is not a JSON object. */
  function parseStreamLine(line) {
    try {
      const value = JSON.parse(line);
      return value && typeof value === "object" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function isBase64(value) {
    return typeof value === "string" && BASE64_RE.test(value);
  }

  /** The server stores attachments as one comma-separated string; the UI works with arrays. */
  function imagesFromField(field) {
    if (!field) return [];
    const parts = Array.isArray(field) ? field : String(field).split(",");
    return parts.map((p) => String(p).trim()).filter(isBase64);
  }

  function mimeFromBase64(b64) {
    if (b64.startsWith("iVBOR")) return "image/png";
    if (b64.startsWith("/9j/")) return "image/jpeg";
    if (b64.startsWith("R0lGOD")) return "image/gif";
    if (b64.startsWith("UklGR")) return "image/webp";
    return "image/png";
  }

  function dataUri(b64) {
    return "data:" + mimeFromBase64(b64) + ";base64," + b64;
  }

  /** First words of a message, used as a session title when the model cannot produce one. */
  function shortTitle(text, max) {
    const flat = String(text || "").replace(/\s+/g, " ").trim();
    if (!flat) return "Image chat";
    return flat.length > max ? flat.slice(0, max - 1).trimEnd() + "…" : flat;
  }

  /** Model-generated title -> single short line without <think> blocks or surrounding quotes. */
  function cleanTitle(raw, max) {
    let title = String(raw || "")
      .replace(/<think>[\s\S]*?(<\/think>|$)/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^["'`“‘]+|["'`”’]+$/g, "")
      .trim();
    if (title.length > max) title = title.slice(0, max - 1).trimEnd() + "…";
    return title;
  }

  return {
    escapeHtml,
    renderModelText,
    createLineSplitter,
    parseStreamLine,
    isBase64,
    imagesFromField,
    mimeFromBase64,
    dataUri,
    shortTitle,
    cleanTitle,
  };
});
