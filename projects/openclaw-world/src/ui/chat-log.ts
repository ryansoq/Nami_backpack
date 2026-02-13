interface ChatLogAPI {
  addMessage(agentId: string, text: string): void;
  addSystem(text: string): void;
}

/**
 * Scrollable chat log panel (bottom-left).
 * Shows broadcast messages and system events.
 */
export function setupChatLog(): ChatLogAPI {
  const container = document.getElementById("chat-log")!;

  const titleEl = document.createElement("div");
  titleEl.className = "chat-title";
  titleEl.textContent = "World Chat";
  container.appendChild(titleEl);

  const messagesEl = document.createElement("div");
  messagesEl.className = "chat-messages";
  container.appendChild(messagesEl);

  // Parse @mentions and make them bold/highlighted
  function parseMentions(text: string): string {
    // Escape HTML first
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    // Highlight @mentions
    return escaped.replace(
      /@(\w+)/g,
      '<span class="chat-mention">@$1</span>'
    );
  }

  function addEntry(className: string, content: string, useHtml = false): void {
    const el = document.createElement("div");
    el.className = `chat-entry ${className}`;
    if (useHtml) {
      el.innerHTML = content;
    } else {
      el.textContent = content;
    }
    messagesEl.appendChild(el);

    // Keep max 100 entries
    while (messagesEl.children.length > 100) {
      messagesEl.removeChild(messagesEl.firstChild!);
    }

    // Auto-scroll to bottom
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  return {
    addMessage(agentId: string, text: string) {
      const time = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      const prefix = `[${time}] <span class="chat-agent">${agentId}</span>: `;
      const content = prefix + parseMentions(text);
      addEntry("chat-msg", content, true);
    },
    addSystem(text: string) {
      addEntry("chat-system", `— ${text}`);
    },
  };
}
