let currentSessionId = null;
let conversationHistory = [];
let imageHistory = [];

document.getElementById('toggleSidebar').addEventListener('click', function() {
  const sidebar = document.getElementById('sidebar');
  const main = document.getElementById('main');
  if (!sidebar.classList.contains('hidden')) {
    setTimeout(() => {
      sidebar.classList.remove('slide-right');
      sidebar.classList.add('hidden');
      this.style.transform = "translateX(-210px)";
      main.classList.add('expanded');      main.classList.add('expanded');

    });
  } else {
    sidebar.classList.remove('hidden');
    sidebar.classList.add('slide-right');
    this.style.transform = "translateX(20px)";
    setTimeout(() => {
      sidebar.classList.remove('slide-right');
      this.style.transform = "";
      main.classList.remove('expanded');
    });
  }
});

// Upload image button triggers file selection
document.getElementById("uploadButton").addEventListener("click", function() {
  document.getElementById("imageUpload").click();
});

// When a file is selected, upload it
document.getElementById("imageUpload").addEventListener("change", async function() {
  if (this.files && this.files[0]) {
    const file = this.files[0];
    const imageBase64 = await uploadImage(file);
    const imageUrl = this.files[0].name;
    console.log(this.files[0]);
    if (imageUrl) {
      console.log("fuck");
      // const chatbox = document.getElementById("userInput");
      const chatbox = document.getElementById("chatbox");
      chatbox.innerHTML += `<div><strong>You:</strong> <br><img src="${imageUrl}" alt="Uploaded Image ${imageUrl}" style="max-width:100%;"></div>`;
      chatbox.scrollTop = chatbox.scrollHeight;
      // Optionally, add the image message to the conversation history
      imageHistory.append(imageBase64);
    }
  }
});

// Function to upload image using FormData
async function uploadImage(file) {
  const formData = new FormData();
  formData.append("image", file);
  try {
    // Replace with your actual image upload endpoint
    const response = await fetch("/deepseek_backend/send_image", {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      throw new Error("Image upload failed");
    }
    const data = await response.json();
    return data.imageBase64;    
    // Assume the response returns an object with an imageUrl property
    
  } catch (error) {
    console.error("Image upload failed:", error);
    return null;
  }
}

async function loadModels() {
  try {
    // Replace the URL below with your actual models endpoint
    const response = await fetch("/deepseek/api/tags");
    const data = await response.json();
    const modelNames = data.models.map(model => model.id || model.name);
    const modelSelect = document.getElementById("modelSelect");
    modelSelect.innerHTML = "";
    modelNames.forEach(name => {
      const option = document.createElement("option");
      option.value = name;
      option.text = name;
      modelSelect.appendChild(option);
    });
  } catch (error) {
    console.error("Error loading models:", error);
  }
}

async function createSession(){
  const response = await fetch("/deepseek_backend/create_session", {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_name: "New Chat" })
  });
  const session = await response.json();
  currentSessionId = session.session_id;
  addSessionToList(session);
  document.getElementById("chatbox").innerHTML = "";
}

function addSessionToList(session) {
  const sessionList = document.getElementById("session-list");
  const container = document.createElement("div");
  container.classList.add("session-container");
  container.setAttribute("data-session-id", session.session_id);
  container.onclick = () => switchSession(session.session_id);
  const nameSpan = document.createElement("span");
  nameSpan.classList.add("session-name");
  nameSpan.innerText = session.session_name;
  const deleteButton = document.createElement("button");
  deleteButton.classList.add("delete-button");
  deleteButton.innerText = "Delete";
  deleteButton.onclick = (e) => {
    e.stopPropagation();
    deleteSession(session.session_id);
    container.remove();
  };
  container.appendChild(nameSpan);
  container.appendChild(deleteButton);
  sessionList.appendChild(container);
}

async function loadSessions(){
  const response = await fetch("/deepseek_backend/get_session");
  const sessions = await response.json();
  const sessionList = document.getElementById("session-list");
  sessionList.innerHTML = "";
  sessions.forEach(session => {
    addSessionToList(session);
  });
}

async function switchSession(sessionId) {
  currentSessionId = sessionId;
  await loadChatHistory(sessionId);
}

async function deleteSession(sessionId = null){
  const idToDelete = sessionId ? sessionId : currentSessionId;
  await fetch('/deepseek_backend/delete_session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: idToDelete })
  });
  loadSessions();
}

async function loadChatHistory(sessionId){
  const response = await fetch(`/deepseek_backend/load_chat/${sessionId}`);
  let messages = await response.json();
  const chatbox = document.getElementById("chatbox");
  chatbox.innerHTML = "";
  messages = messages.reverse();
  messages.forEach(msg => {
    chatbox.innerHTML += `<div><strong>${msg.role === "user" ? "You" : "Robot"}:</strong> ${msg.content}</div>`;
  });
  conversationHistory = messages;
  chatbox.scrollTop = chatbox.scrollHeight;
  let newSessionName = await computeSessionName(messages);
  updateSessionName(sessionId, newSessionName);
}

async function computeSessionName(messages) {
  if (messages.length > 0) {
    for (let msg of messages) {
      if (msg.content && msg.content.trim() !== "") {
        const response = await fetch('/deepseek/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: "deepseek-llm:7b",
            prompt: `Summarize the following content in no more than 10 words, less is better:\n\n${msg.content}`,
            stream: false
          })
        });
        const data = await response.json();
        return data.response;
      }
    }
  }
  return "New Chat";
}

function updateSessionName(sessionId, newName) {
  const sessionList = document.getElementById("session-list");
  const container = sessionList.querySelector(`[data-session-id="${sessionId}"]`);
  if (container) {
    const nameSpan = container.querySelector(".session-name");
    if (nameSpan) {
      nameSpan.innerText = newName;
    }
  }
}

function formatThinkText(text) {
  return text.replace(/<think>([\s\S]*?)<\/think>/g, '<span class="think-text">$1</span>');
}

async function sendMessage() {
  if (!currentSessionId) {
    alert("Please select or create a session first.");
    return;
  }
  const userInputElem = document.getElementById('userInput');
  const userInput = userInputElem.value;
  const chatbox = document.getElementById('chatbox');

  chatbox.innerHTML += `<div><strong>You:</strong> ${userInput}</div>`;
  chatbox.scrollTop = chatbox.scrollHeight;
  if(imageHistory.length > 0){
    conversationHistory.push({ role: "user", content: userInput, images: imageHistory });
  }
  else{
    conversationHistory.push({ role: "user", content: userInput });
  }
  const recentHistory = conversationHistory.slice(-10);
  
  // Use the selected model from the dropdown
  const selectedModel = document.getElementById("modelSelect").value;
  console.log(selectedModel);

  const responseDiv = document.createElement("div");
  responseDiv.innerHTML = `<strong>Robot:</strong> <span class="streaming-response"></span>`;
  chatbox.appendChild(responseDiv);
  chatbox.scrollTop = chatbox.scrollHeight;

  try {
    const response = await fetch('/deepseek/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: selectedModel,
        messages: recentHistory,
        stream: true
      })
    });

    if (!response.body) throw new Error("No response body from server.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedResponse = "";
    let buffer = "";
    const responseSpan = document.querySelectorAll(".streaming-response");
    const latestResponseSpan = responseSpan[responseSpan.length - 1];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n");
      while (boundary !== -1) {
        let jsonChunk = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 1);
        boundary = buffer.indexOf("\n");
        if (jsonChunk) {
          try {
            const parsedChunk = JSON.parse(jsonChunk);
            if (parsedChunk.message && parsedChunk.message.content) {
              let chunkText = parsedChunk.message.content;
              chunkText = formatThinkText(chunkText);
              accumulatedResponse += chunkText;
              latestResponseSpan.innerHTML = accumulatedResponse;
              chatbox.scrollTop = chatbox.scrollHeight;
            }
          } catch (e) {
            console.error("Error parsing chunk:", e);
          }
        }
      }
    }
    conversationHistory.push({ role: "assistant", content: accumulatedResponse });
    await fetch("/deepseek_backend/save_chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId,
        user: userInput,
        assistant: accumulatedResponse
      })
    });
  } catch (error) {
    chatbox.innerHTML += `<div><strong>Error:</strong> ${error.message}</div>`;
  }
  userInputElem.value = '';
  imageHistory = [];
}

window.onload = function(){
  loadSessions();
  loadModels();
  if(currentSessionId){
    loadChatHistory(currentSessionId);
  }
};
