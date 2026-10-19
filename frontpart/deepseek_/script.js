/*
 * Chat page. Talks to two endpoints served by backpart/DeepSeek/server.py:
 *   /deepseek_backend/*  sessions, history and image uploads (SQLite)
 *   /deepseek/api/*      LLM proxy (model list, streaming chat, one-shot generate)
 * Pure helpers live in chat-render.js.
 */
(function () {
  "use strict";

  const R = window.ChatRender;
  const metaRoot = document.querySelector('meta[name="chat-api-root"]');
  const API_ROOT = ((metaRoot && metaRoot.content) || "").replace(/\/$/, "");
  const BACKEND = API_ROOT + "/deepseek_backend";
  const LLM_API = API_ROOT + "/deepseek/api";

  const DEFAULT_TITLE = "New Chat";
  const MAX_IMAGES = 4;
  const CONTEXT_MESSAGES = 10; // how many past messages are sent to the model
  const NARROW = window.matchMedia("(max-width: 720px)");

  const el = {
    toggle: document.getElementById("toggleSidebar"),
    sidebar: document.getElementById("sidebar"),
    newSession: document.getElementById("newSession"),
    sessionList: document.getElementById("session-list"),
    model: document.getElementById("modelSelect"),
    status: document.getElementById("status"),
    chatbox: document.getElementById("chatbox"),
    attachments: document.getElementById("attachments"),
    form: document.getElementById("input-area"),
    input: document.getElementById("userInput"),
    upload: document.getElementById("uploadButton"),
    send: document.getElementById("sendButton"),
    file: document.getElementById("imageUpload"),
  };

  let currentSessionId = null;
  let history = []; // [{role, content, images: string[]}] for the active session
  let pendingImages = []; // base64 strings attached to the message being composed
  let busy = false;
  const sessionNames = new Map(); // id -> title currently shown

  // ---------------------------------------------------------------- helpers

  async function api(url, options) {
    const resp = await fetch(url, options);
    let data = null;
    try {
      data = await resp.json();
    } catch (e) {
      /* non-JSON body */
    }
    if (!resp.ok) {
      throw new Error((data && data.error) || "Request failed (HTTP " + resp.status + ")");
    }
    return data;
  }

  function postJson(url, body) {
    return api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function showStatus(message, kind) {
    el.status.textContent = message;
    el.status.className = kind || "info";
    el.status.hidden = !message;
  }

  function scrollToEnd() {
    el.chatbox.scrollTop = el.chatbox.scrollHeight;
  }

  function setBusy(value) {
    busy = value;
    el.send.disabled = value;
    el.send.textContent = value ? "Sending…" : "Send";
  }

  // ---------------------------------------------------------------- sidebar

  function setSidebar(open) {
    document.body.classList.toggle("sidebar-collapsed", !open);
    el.toggle.setAttribute("aria-expanded", String(open));
  }

  el.toggle.addEventListener("click", function () {
    setSidebar(document.body.classList.contains("sidebar-collapsed"));
  });

  // ---------------------------------------------------------------- sessions

  function markActiveSession() {
    el.sessionList.querySelectorAll(".session-container").forEach(function (node) {
      const active = Number(node.dataset.sessionId) === currentSessionId;
      node.classList.toggle("active", active);
      const name = node.querySelector(".session-name");
      if (active) name.setAttribute("aria-current", "true");
      else name.removeAttribute("aria-current");
    });
  }

  function addSessionToList(session, prepend) {
    sessionNames.set(session.session_id, session.session_name);
    const container = document.createElement("div");
    container.className = "session-container";
    container.dataset.sessionId = session.session_id;

    const nameButton = document.createElement("button");
    nameButton.type = "button";
    nameButton.className = "session-name";
    nameButton.textContent = session.session_name;
    nameButton.addEventListener("click", function () {
      switchSession(session.session_id);
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-button";
    deleteButton.textContent = "Delete";
    deleteButton.setAttribute("aria-label", "Delete session " + session.session_name);
    deleteButton.addEventListener("click", function () {
      deleteSession(session.session_id);
    });

    container.append(nameButton, deleteButton);
    if (prepend) el.sessionList.prepend(container);
    else el.sessionList.append(container);
  }

  async function loadSessions() {
    const sessions = await api(BACKEND + "/get_session");
    el.sessionList.replaceChildren();
    sessions.forEach(function (s) {
      addSessionToList(s, false);
    });
    markActiveSession();
  }

  async function createSession() {
    const session = await postJson(BACKEND + "/create_session", { session_name: DEFAULT_TITLE });
    currentSessionId = session.session_id;
    history = [];
    pendingImages = [];
    renderAttachments();
    el.chatbox.replaceChildren();
    addSessionToList({ session_id: session.session_id, session_name: session.session_name || DEFAULT_TITLE }, true);
    markActiveSession();
    return session;
  }

  async function ensureSession() {
    if (currentSessionId === null) await createSession();
  }

  async function switchSession(sessionId) {
    currentSessionId = sessionId;
    markActiveSession();
    pendingImages = [];
    renderAttachments();
    try {
      const messages = await api(BACKEND + "/load_chat/" + sessionId);
      history = messages.map(function (m) {
        return { role: m.role, content: m.content || "", images: R.imagesFromField(m.images) };
      });
      el.chatbox.replaceChildren();
      history.forEach(function (m) {
        appendMessage(m.role, m.content, m.images);
      });
      showStatus("");
    } catch (e) {
      showStatus("Could not load this session: " + e.message, "error");
    }
    if (NARROW.matches) setSidebar(false);
  }

  async function deleteSession(sessionId) {
    try {
      await postJson(BACKEND + "/delete_session", { session_id: sessionId });
    } catch (e) {
      showStatus("Could not delete the session: " + e.message, "error");
      return;
    }
    sessionNames.delete(sessionId);
    if (sessionId === currentSessionId) {
      currentSessionId = null;
      history = [];
      el.chatbox.replaceChildren();
    }
    await loadSessions();
  }

  function updateSessionName(sessionId, name) {
    sessionNames.set(sessionId, name);
    const node = el.sessionList.querySelector('[data-session-id="' + sessionId + '"]');
    if (!node) return;
    node.querySelector(".session-name").textContent = name;
    node.querySelector(".delete-button").setAttribute("aria-label", "Delete session " + name);
  }

  // First message of a session -> short title (model-generated, or the first words as a fallback).
  async function titleSession(sessionId, firstMessage, model) {
    if (sessionNames.get(sessionId) !== DEFAULT_TITLE) return;
    sessionNames.set(sessionId, "…"); // claim it so concurrent sends do not title twice
    let title = R.shortTitle(firstMessage, 40);
    if (firstMessage.trim()) {
      try {
        const out = await postJson(LLM_API + "/generate", {
          model: model || undefined,
          prompt: "Summarize the following content in no more than 10 words, less is better:\n\n" + firstMessage,
          stream: false,
        });
        const generated = R.cleanTitle(out.response, 60);
        if (generated.length >= 3) title = generated; // tiny models sometimes answer with one or two letters
      } catch (e) {
        /* keep the fallback title */
      }
    }
    try {
      await postJson(BACKEND + "/rename_session", { session_id: sessionId, session_name: title });
      updateSessionName(sessionId, title);
    } catch (e) {
      sessionNames.set(sessionId, DEFAULT_TITLE);
    }
  }

  // ---------------------------------------------------------------- messages

  function appendMessage(role, text, images) {
    const row = document.createElement("div");
    row.className = "message " + role;
    const label = document.createElement("strong");
    label.textContent = role === "user" ? "You:" : role === "error" ? "Error:" : "Robot:";
    const body = document.createElement("span");
    body.className = "body";
    if (role === "assistant") body.innerHTML = R.renderModelText(text); // escaped by renderModelText
    else body.textContent = text;
    row.append(label, " ", body);
    (images || []).forEach(function (b64, i) {
      const img = document.createElement("img");
      img.className = "chat-image";
      img.src = R.dataUri(b64);
      img.alt = "Attached image " + (i + 1);
      row.append(img);
    });
    el.chatbox.append(row);
    scrollToEnd();
    return body;
  }

  function renderAttachments() {
    el.attachments.replaceChildren();
    el.attachments.hidden = pendingImages.length === 0;
    pendingImages.forEach(function (b64, i) {
      const item = document.createElement("span");
      item.className = "attachment";
      const img = document.createElement("img");
      img.src = R.dataUri(b64);
      img.alt = "Attached image " + (i + 1);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", "Remove attached image " + (i + 1));
      remove.addEventListener("click", function () {
        pendingImages.splice(i, 1);
        renderAttachments();
      });
      item.append(img, remove);
      el.attachments.append(item);
    });
  }

  async function streamReply(model, outgoing, onText) {
    const resp = await fetch(LLM_API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: model || undefined, messages: outgoing, stream: true }),
    });
    if (!resp.ok) {
      let message = "Chat request failed (HTTP " + resp.status + ")";
      try {
        message = (await resp.json()).error || message;
      } catch (e) {
        /* keep generic message */
      }
      throw new Error(message);
    }
    if (!resp.body) throw new Error("No response body from server.");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    const splitter = R.createLineSplitter();
    let text = "";
    function handle(line) {
      const chunk = R.parseStreamLine(line);
      if (!chunk) return;
      if (chunk.error) throw new Error(chunk.error);
      if (chunk.message && chunk.message.content) {
        text += chunk.message.content;
        onText(text);
      }
    }
    for (;;) {
      const step = await reader.read();
      if (step.done) break;
      splitter.push(decoder.decode(step.value, { stream: true })).forEach(handle);
    }
    splitter.flush().forEach(handle);
    return text;
  }

  async function sendMessage() {
    if (busy) return;
    const text = el.input.value.trim();
    if (!text && pendingImages.length === 0) return;
    try {
      await ensureSession();
    } catch (e) {
      showStatus("Could not start a session: " + e.message, "error");
      return;
    }

    setBusy(true);
    showStatus("");
    const sessionId = currentSessionId;
    const images = pendingImages.slice();
    const model = el.model.value;
    const outgoing = history
      .slice(-CONTEXT_MESSAGES)
      .concat([{ role: "user", content: text, images: images }]);

    appendMessage("user", text, images);
    el.input.value = "";
    pendingImages = [];
    renderAttachments();

    const botBody = appendMessage("assistant", "");
    let reply = "";
    try {
      reply = await streamReply(model, outgoing, function (partial) {
        reply = partial;
        botBody.innerHTML = R.renderModelText(partial);
        scrollToEnd();
      });
      if (!reply.trim()) throw new Error("The model returned an empty response.");
    } catch (e) {
      if (!reply.trim()) botBody.closest(".message").remove();
      appendMessage("error", e.message);
      setBusy(false);
      el.input.focus();
      return;
    }

    history.push({ role: "user", content: text, images: images }, { role: "assistant", content: reply, images: [] });
    try {
      await postJson(BACKEND + "/save_chat", {
        session_id: sessionId,
        user: text,
        assistant: reply,
        images: images,
      });
      titleSession(sessionId, text, model);
    } catch (e) {
      appendMessage("error", "The reply could not be saved: " + e.message);
    }
    setBusy(false);
    el.input.focus();
  }

  // ---------------------------------------------------------------- uploads

  el.upload.addEventListener("click", function () {
    el.file.click();
  });

  el.file.addEventListener("change", async function () {
    const file = el.file.files && el.file.files[0];
    el.file.value = "";
    if (!file) return;
    if (pendingImages.length >= MAX_IMAGES) {
      showStatus("At most " + MAX_IMAGES + " images per message.", "error");
      return;
    }
    try {
      await ensureSession();
      const form = new FormData();
      form.append("image", file);
      const data = await api(BACKEND + "/get_base64/" + currentSessionId, { method: "POST", body: form });
      pendingImages.push(data.imageBase64);
      renderAttachments();
      showStatus("");
    } catch (e) {
      showStatus("Upload failed: " + e.message, "error");
    }
  });

  // ---------------------------------------------------------------- models

  async function loadModels() {
    try {
      const data = await api(LLM_API + "/tags");
      const names = data.models.map(function (m) {
        return m.id || m.name;
      });
      el.model.replaceChildren();
      names.forEach(function (name) {
        el.model.append(new Option(name, name));
      });
      if (data.warning) {
        showStatus("Could not list models from the LLM server (" + data.warning + "). Using the default model.", "warn");
      }
    } catch (e) {
      el.model.replaceChildren(new Option("No models available", ""));
      showStatus("Model list unavailable: " + e.message, "warn");
    }
  }

  // ---------------------------------------------------------------- wiring

  el.newSession.addEventListener("click", async function () {
    try {
      await createSession();
      if (NARROW.matches) setSidebar(false);
      el.input.focus();
    } catch (e) {
      showStatus("Could not create a session: " + e.message, "error");
    }
  });

  el.form.addEventListener("submit", function (event) {
    event.preventDefault();
    sendMessage();
  });

  el.input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendMessage();
    }
  });

  setSidebar(!NARROW.matches);
  loadSessions().catch(function (e) {
    showStatus(
      "Chat backend not reachable (" + e.message + "). This page needs the Flask server in backpart/DeepSeek; see the README.",
      "error"
    );
  });
  loadModels();
})();
