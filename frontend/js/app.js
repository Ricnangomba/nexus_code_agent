function checkAuth() {
    const logged = localStorage.getItem("loggedIn");
    const appEl = document.getElementById("app");
    if (logged === "true") {
        if (appEl) appEl.style.display = "block";
    } else {
        // Redirect to login page
        window.location.href = "/login.html";
    }
}

// Ensure app is hidden by default until auth check
document.addEventListener("DOMContentLoaded", () => {
    const appEl = document.getElementById("app");
    if (appEl) appEl.style.display = "none";
});
// Main application logic and event handlers

const API = {
    base: "",
    
    async request(path, options = {}) {
        const response = await fetch(this.base + path, {
            headers: {
                "Content-Type": "application/json",
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || error.message || "Request failed");
        }
        
        return response.json();
    },
    
    get(path) {
        return this.request(path);
    },
    
    post(path, data) {
        return this.request(path, {
            method: "POST",
            body: JSON.stringify(data)
        });
    },
    
    delete(path) {
        return this.request(path, {
            method: "DELETE"
        });
    }
};

const Cache = {
    set: (key, val) => localStorage.setItem(key, JSON.stringify(val)),
    get: (key) => JSON.parse(localStorage.getItem(key)),
    remove: (key) => localStorage.removeItem(key)
};

const debounce = (fn, delay) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), delay);
    };
};

const state = {
    currentProject: null,
    currentFile: null,
    fileContent: "",
    editor: null,
    terminal: null,
    terminalBuffer: "",
    ws: null,
    chatWs: null,
    isStreaming: false,
    skills: [],
    extensions: [],
    chatHistory: []
};

const saveState = () => {
    Cache.set("nexus_state", {
        currentProject: state.currentProject,
        currentFile: state.currentFile,
        chatHistory: state.chatHistory,
        terminalBuffer: state.terminalBuffer
    });
};

const loadState = () => {
    const saved = Cache.get("nexus_state");
    if (saved) {
        state.currentProject = saved.currentProject;
        state.currentFile = saved.currentFile;
        state.chatHistory = saved.chatHistory || [];
        state.terminalBuffer = saved.terminalBuffer || "";
    }
};

const commandPaletteCommands = [
    { id: "install_extension", label: "Install Extension", action: importExtension },
    { id: "open_settings", label: "Open Settings", action: () => document.getElementById("settingsModal").classList.add("active") },
    { id: "open_ai", label: "Open AI Chat", action: () => document.querySelector(".tab[data-view='ai']").click() },
    { id: "new_project", label: "New Project", action: () => document.getElementById("newProjectModal").classList.add("active") }
];

// Initialization
document.addEventListener("DOMContentLoaded", async () => {
    loadState();
    showLoading("Starting Nexus...");
    try {
        await loadStatus();
        setupMonaco();
        setupTabs();
        setupSidebar();
        setupModals();
        setupChat();
        setupTerminal();
        setupKeyboard();
        setupProjectHandlers();
        await loadProjects();
        await loadLLMStatus();
        hideLoading();
        notify("Welcome to Nexus Code Agent!", "success");
        state.chatHistory.forEach(msg => addMessage(msg.role, msg.content, msg.isHTML));
    } catch (e) {
        console.error(e);
        hideLoading();
        notify("Failed: " + e.message, "error");
    }
});

// ==================== MONACO EDITOR ====================
function setupMonaco() {
    require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
    require(["vs/editor/editor.main"], () => {
        monaco.editor.defineTheme("nexus-dark", {
            base: "vs-dark",
            inherit: true,
            rules: [],
            colors: {
                "editor.background": "#0d1117",
                "editor.foreground": "#e6edf3",
                "editorLineNumber.foreground": "#6e7681",
                "editorCursor.foreground": "#58a6ff"
            }
        });
        
        state.editor = monaco.editor.create(document.getElementById("monaco-editor"), {
            value: "// Welcome to Nexus Code Agent!\n// Create or select a project from the sidebar.\n\n// Press Ctrl+S to save, Ctrl+Enter to run\n// Click AI button to chat with Nexus\n",
            language: "javascript",
            theme: "nexus-dark",
            fontSize: 14,
            fontFamily: "SF Mono, Monaco, Consolas, monospace",
            minimap: { enabled: true },
            automaticLayout: true,
            wordWrap: "on",
            scrollBeyondLastLine: false,
            smoothScrolling: true,
            tabSize: 4
        });
        
        state.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveCurrentFile);
        state.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, runCode);
        state.editor.onDidChangeModelContent(debounce(() => {
            state.fileContent = state.editor.getValue();
            updateBreadcrumbs();
        }, 500));
    });
}

// ==================== TABS ====================
function setupTabs() {
    document.querySelectorAll(".tab").forEach(tab => {
        tab.addEventListener("click", () => {
            const view = tab.dataset.view;
            document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById("view" + view.charAt(0).toUpperCase() + view.slice(1)).classList.add("active");

            if (view === "terminal" && state.terminal) {
                setTimeout(() => state.terminal.fit(), 50);
            }
            if (view === "preview") {
                updatePreview();
            }
        });
    });
    
    document.getElementById("aiBtn").addEventListener("click", () => {
        document.querySelector(".tab[data-view='ai']").click();
    });
}

// ==================== SIDEBAR ====================
function setupSidebar() {
    document.getElementById("toggleSidebar").addEventListener("click", () => {
        document.getElementById("sidebar").classList.toggle("collapsed");
    });
    
    document.getElementById("newProjectBtn").addEventListener("click", () => {
        document.getElementById("newProjectModal").classList.add("active");
    });
    
    document.getElementById("newFileBtn").addEventListener("click", () => {
        if (!state.currentProject) {
            notify("Select a project first", "warning");
            return;
        }
        const name = prompt("New file name:");
        if (name) {
            API.post("/api/file/write", { project: state.currentProject, path: name, content: "" })
                .then(() => {
                    loadFileTree(state.currentProject);
                    notify("Created " + name, "success");
                })
                .catch(e => notify("Failed: " + e.message, "error"));
        }
    });
    
    document.getElementById("settingsBtn").addEventListener("click", () => {
        document.getElementById("settingsModal").classList.add("active");
        loadSettings();
    });
    document.getElementById("installExtensionBtn").addEventListener("click", openCommandPalette);
}

// ==================== MODALS ====================
function setupModals() {
    // Close modals on escape
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            document.querySelectorAll(".modal.active").forEach(m => m.classList.remove("active"));
            closeCommandPalette();
        }
    });
    document.getElementById("importSkillBtn").addEventListener("click", importSkill);
    document.getElementById("importExtensionBtn").addEventListener("click", importExtension);
}

function openCommandPalette() {
    const modal = document.getElementById("commandPaletteModal");
    const input = document.getElementById("commandPaletteInput");
    if (!modal || !input) return;
    modal.classList.add("active");
    input.value = "";
    input.focus();
    renderCommandPaletteList(commandPaletteCommands);
}

function closeCommandPalette() {
    const modal = document.getElementById("commandPaletteModal");
    if (modal) {
        modal.classList.remove("active");
    }
}

function renderCommandPaletteList(commands) {
    const list = document.getElementById("commandPaletteList");
    if (!list) return;
    list.innerHTML = commands.map(cmd => `
        <div class="command-item" data-command="${cmd.id}">${cmd.label}</div>
    `).join("");
    list.querySelectorAll(".command-item").forEach(item => {
        item.addEventListener("click", () => {
            const command = commandPaletteCommands.find(cmd => cmd.id === item.dataset.command);
            if (command) {
                closeCommandPalette();
                command.action();
            }
        });
    });
}

function filterCommandPalette(query) {
    const term = query.trim().toLowerCase();
    const filtered = term
        ? commandPaletteCommands.filter(cmd => cmd.label.toLowerCase().includes(term))
        : commandPaletteCommands;
    renderCommandPaletteList(filtered);
}

// ==================== PROJECTS ====================
async function loadProjects() {
    try {
        const data = await API.get("/api/projects");
        const list = document.getElementById("projectList");
        
        if (!data.projects || !data.projects.length) {
            list.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">
                <i class="fas fa-folder-open" style="font-size: 24px; margin-bottom: 8px; display: block;"></i>
                No projects yet.<br>Click + to create one.
            </div>`;
            return;
        }
        
        list.innerHTML = data.projects.map(p => `
            <div class="project-item ${p.name === state.currentProject ? "active" : ""}" data-project="${p.name}">
                <i class="fas fa-${getProjectIcon(p.template)} icon"></i>
                <span class="project-name" title="${p.description || p.name}">${p.name}</span>
                <button class="icon-btn-sm" onclick="event.stopPropagation(); deleteProject('${p.name}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `).join("");
        
        list.querySelectorAll(".project-item").forEach(item => {
            item.addEventListener("click", () => openProject(item.dataset.project));
        });
    } catch (e) {
        console.error("Load projects failed:", e);
    }
}

function getProjectIcon(template) {
    const icons = {
        python: "fa-python",
        react: "fa-react",
        html: "fa-html5",
        node: "fa-node-js",
        flask: "fa-flask",
        blank: "fa-file"
    };
    return icons[template] || "fa-folder";
}

async function createProject() {
    const name = document.getElementById("projectName").value;
    const template = document.getElementById("projectTemplate").value;
    const description = document.getElementById("projectDescription").value;
    
    if (!name) {
        notify("Project name required", "warning");
        return;
    }
    
    try {
        await API.post("/api/projects", { name, template, description });
        document.getElementById("projectName").value = "";
        document.getElementById("projectDescription").value = "";
        document.getElementById("newProjectModal").classList.remove("active");
        await loadProjects();
        notify("Project created", "success");
    } catch (e) {
        notify("Failed: " + e.message, "error");
    }
}

async function openProject(name) {
    state.currentProject = name;
    state.currentFile = null;
    saveState();
    document.querySelectorAll(".project-item").forEach(item => {
        item.classList.toggle("active", item.dataset.project === name);
    });
    document.getElementById("filesSection").style.display = "block";
    await loadFileTree(name);
    updateBreadcrumbs();
    setTimeout(() => {
        const f = document.querySelector('.file-tree-item[data-type="file"]');
        if (f) f.click();
    }, 100);
}

async function deleteProject(name) {
    if (!confirm(`Delete project "${name}"?`)) return;
    try {
        await API.delete(`/api/projects/${name}`);
        if (state.currentProject === name) {
            state.currentProject = null;
            state.currentFile = null;
            saveState();
            state.editor.setValue("// Project deleted");
            document.getElementById("filesSection").style.display = "none";
        }
        await loadProjects();
        notify("Deleted " + name, "success");
    } catch (e) {
        notify("Delete failed: " + e.message, "error");
    }
}

// ==================== FILE TREE ====================
async function loadFileTree(projectName) {
    try {
        const tree = await API.get(`/api/projects/${projectName}/files`);
        renderFileTree(tree.tree, document.getElementById("fileTree"));
    } catch (e) {
        console.error("File tree failed:", e);
    }
}

function renderFileTree(node, container, basePath = "") {
    container.innerHTML = "";
    if (!node || !node.children) return;
    
    const sorted = node.children.sort((a, b) =>
        a.type !== b.type ? (a.type === "directory" ? -1 : 1) : a.name.localeCompare(b.name)
    );
    
    for (const child of sorted) {
        if (child.type === "directory") {
            const dirEl = document.createElement("div");
            dirEl.className = "file-tree-dir";
            dirEl.innerHTML = `
                <div class="file-tree-item" data-type="dir" data-path="${basePath}${child.name}/">
                    <i class="fas fa-chevron-down icon" style="font-size: 9px;"></i>
                    <i class="fas fa-folder icon"></i>
                    <span>${child.name}</span>
                </div>
                <div class="file-tree-children" id="dir-${basePath}${child.name}"></div>
            `;
            container.appendChild(dirEl);
            
            const header = dirEl.querySelector(".file-tree-item");
            header.addEventListener("click", (e) => {
                e.stopPropagation();
                const c = dirEl.querySelector(".file-tree-children");
                const i = header.querySelector(".fa-chevron-down");
                c.style.display = c.style.display === "none" ? "block" : "none";
                i.style.transform = c.style.display === "none" ? "rotate(-90deg)" : "";
            });
            
            if (child.children && child.children.length) {
                renderFileTree(child, dirEl.querySelector(".file-tree-children"), `${basePath}${child.name}/`);
            }
        } else {
            const fileEl = document.createElement("div");
            fileEl.className = "file-tree-item";
            fileEl.dataset.type = "file";
            fileEl.dataset.path = `${basePath}${child.name}`;
            fileEl.innerHTML = `
                <i class="fas ${getFileIcon(child.name)} icon"></i>
                <span>${child.name}</span>
                <div class="file-actions">
                    <button onclick="event.stopPropagation(); deleteFile('${basePath}${child.name}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            fileEl.addEventListener("click", () => openFile(`${basePath}${child.name}`));
            container.appendChild(fileEl);
        }
    }
}

function getFileIcon(filename) {
    const ext = filename.split(".").pop().toLowerCase();
    const icons = {
        py: "fa-python", js: "fa-js", jsx: "fa-react", ts: "fa-code", tsx: "fa-react",
        html: "fa-html5", css: "fa-css3-alt", json: "fa-brackets-curly", md: "fa-markdown",
        java: "fa-java", cpp: "fa-code", c: "fa-code", go: "fa-code", rs: "fa-code",
        rb: "fa-gem", php: "fa-php", sh: "fa-terminal", swift: "fa-code", kt: "fa-code",
        sql: "fa-database", txt: "fa-file-alt", yml: "fa-file-code", yaml: "fa-file-code"
    };
    return icons[ext] || "fa-file-code";
}

async function openFile(path) {
    if (!state.currentProject) return;
    try {
        const data = await API.post("/api/file/read", { project: state.currentProject, path });
        state.currentFile = path;
        state.fileContent = data.content;
        saveState();
        
        if (state.editor) {
            const ext = path.split(".").pop();
            monaco.editor.setModelLanguage(state.editor.getModel(), detectLanguage(ext));
            state.editor.setValue(data.content);
        }
        
        document.querySelectorAll('.file-tree-item[data-type="file"]').forEach(el => {
            el.classList.toggle("active", el.dataset.path === path);
        });
        updateBreadcrumbs();
    } catch (e) {
        notify("Failed to open: " + e.message, "error");
    }
}

function detectLanguage(ext) {
    const langs = {
        py: "python", js: "javascript", ts: "typescript", jsx: "javascript", tsx: "typescript",
        java: "java", cpp: "cpp", c: "c", h: "cpp", cs: "csharp", rs: "rust", go: "go",
        rb: "ruby", php: "php", html: "html", htm: "html", css: "css", scss: "scss",
        json: "json", md: "markdown", xml: "xml", sh: "shell", bash: "shell",
        yml: "yaml", yaml: "yaml", sql: "sql", swift: "swift", kt: "kotlin"
    };
    return langs[ext] || "plaintext";
}

async function saveCurrentFile() {
    if (!state.currentFile || !state.currentProject) {
        notify("No file to save", "warning");
        return;
    }
    try {
        await API.post("/api/file/write", {
            project: state.currentProject,
            path: state.currentFile,
            content: state.editor.getValue()
        });
        notify("Saved " + state.currentFile, "success");
    } catch (e) {
        notify("Save failed: " + e.message, "error");
    }
}

async function deleteFile(path) {
    if (!confirm(`Delete "${path}"?`)) return;
    try {
        await API.post("/api/file/delete", { project: state.currentProject, path });
        if (state.currentFile === path) {
            state.currentFile = null;
            saveState();
            state.editor.setValue("");
        }
        await loadFileTree(state.currentProject);
        notify("File deleted", "success");
    } catch (e) {
        notify("Delete failed: " + e.message, "error");
    }
}

function updateBreadcrumbs() {
    const el = document.getElementById("breadcrumbs");
    if (!state.currentProject) {
        el.innerHTML = '<span class="breadcrumb-item">No project</span>';
        return;
    }

    let html = `<span class="breadcrumb-item">${state.currentProject}</span>`;
    if (state.currentFile) {
        html += '<span class="breadcrumb-separator">/</span>';
        const parts = state.currentFile.split("/");
        const file = parts.pop();
        if (parts.length > 0) {
            html += `<span class="breadcrumb-item">${parts.join("/")}</span><span class="breadcrumb-separator">/</span>`;
        }
        html += `<span class="breadcrumb-item active">${file}</span>`;
    }
    el.innerHTML = html;
}

/**
 * Refreshes the preview iframe with the current editor content.
 * If no file is open, displays a placeholder message.
 */
function updatePreview() {
    const iframe = document.getElementById("previewIframe");
    if (!iframe) return;
    if (!state.currentFile) {
        iframe.srcdoc = '<p>No file selected for preview.</p>';
        return;
    }
    // Use the editor's current value as the HTML source.
    const content = state.editor ? state.editor.getValue() : '';
    iframe.srcdoc = content;
}

// ==================== CHAT ====================
function setupChat() {
    const input = document.getElementById("aiInput");
    const sendBtn = document.getElementById("aiSend");
    
    const send = async () => {
        const message = input.value.trim();
        if (!message || state.isStreaming) return;
        
        input.value = "";
        input.style.height = "auto";
        
        const welcome = document.querySelector(".ai-welcome");
        if (welcome) welcome.remove();
        
        addMessage("user", message);
        state.chatHistory.push({ role: "user", content: message });
        saveState();
        
        const useAgent = document.getElementById("useAgent").checked;
        if (useAgent) await runAgent(message);
        else await runChat(message);
    };
    
    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });
    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 200) + "px";
    });
    
    document.querySelectorAll(".suggestion-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            input.value = chip.dataset.prompt;
            input.focus();
            send();
        });
    });
}

function addMessage(role, content, isHTML = false) {
    const container = document.getElementById("aiMessages");
    const msg = document.createElement("div");
    msg.className = `message ${role}`;
    msg.innerHTML = `
        <div class="message-avatar"><i class="fas fa-${role === "user" ? "user" : "robot"}"></i></div>
        <div class="message-content">${isHTML ? content : '<div class="message-text">' + formatMarkdown(content) + '</div>'}</div>
    `;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    return msg.querySelector(".message-text") || msg.querySelector(".message-content");
}

async function runChat(message) {
    state.isStreaming = true;
    document.getElementById("aiSend").disabled = true;
    const textEl = addMessage("assistant", '<i class="fas fa-spinner fa-spin"></i> Thinking...', true);
    
    try {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${protocol}//${location.host}/ws/chat`);
        
        await new Promise((res, rej) => {
            ws.onopen = res;
            ws.onerror = rej;
        });
        
        let fullText = "";
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "chunk") {
                fullText += data.content;
                textEl.innerHTML = formatMarkdown(fullText);
                document.getElementById("aiMessages").scrollTop = document.getElementById("aiMessages").scrollHeight;
            } else if (data.type === "error") {
                textEl.innerHTML = `<span style="color: var(--error)">Error: ${data.message}</span>`;
            } else if (data.type === "done") {
                state.chatHistory.push({ role: "assistant", content: fullText });
                saveState();
                ws.close();
            }
        };
        
        ws.send(JSON.stringify({ message }));
    } catch (e) {
        textEl.innerHTML = `<span style="color: var(--error)">Error: ${e.message}</span>`;
    } finally {
        state.isStreaming = false;
        document.getElementById("aiSend").disabled = false;
    }
}

async function runAgent(task) {
    state.isStreaming = true;
    document.getElementById("aiSend").disabled = true;
    const textEl = addMessage("assistant", '<i class="fas fa-spinner fa-spin"></i> Agent working...', true);
    
    try {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${protocol}//${location.host}/ws/agent`);
        
        await new Promise((res, rej) => {
            ws.onopen = res;
            ws.onerror = rej;
        });
        
        let stepsHtml = "";
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "step") {
                stepsHtml += `<div class="message-step">
                    <div class="step-label"><i class="fas fa-lightbulb"></i> Thought</div>
                    <div>${escapeHtml(data.thought || "")}</div>
                    <div class="step-label" style="margin-top: 6px;"><i class="fas fa-cog"></i> Action: ${escapeHtml(data.action || "")}</div>
                    <pre>${escapeHtml(JSON.stringify(data.action_input || {}, null, 2))}</pre>
                </div>`;
                textEl.innerHTML = stepsHtml;
                document.getElementById("aiMessages").scrollTop = document.getElementById("aiMessages").scrollHeight;
            } else if (data.type === "done") {
                state.chatHistory.push({ role: "assistant", content: stepsHtml, isHTML: true });
                saveState();
                ws.close();
            }
        };
        
        ws.send(JSON.stringify({ task }));
    } catch (e) {
        textEl.innerHTML = `<span style="color: var(--error)">Error: ${e.message}</span>`;
    } finally {
        state.isStreaming = false;
        document.getElementById("aiSend").disabled = false;
    }
}

// ==================== TERMINAL ====================


// ==================== PROJECT HANDLERS ====================
function setupProjectHandlers() {
    // Can add more project event handlers here
}

// ==================== UTILITIES ====================
async function loadStatus() {
    try {
        const data = await API.get("/api/status");
        console.log("Server status:", data);
    } catch (e) {
        console.error("Status check failed:", e);
    }
}

async function loadLLMStatus() {
    try {
        const data = await API.get("/api/tools");
        console.log("Available tools:", data.tools);
    } catch (e) {
        console.error("LLM status check failed:", e);
    }
}

function formatMarkdown(text) {
    // Simple markdown to HTML
    text = escapeHtml(text);
    text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");
    text = text.replace(/`(.*?)`/g, "<code>$1</code>");
    text = text.replace(/\n/g, "<br>");
    return text;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function showLoading(message) {
    // Show loading indicator
    console.log(message);
}

function hideLoading() {
    // Hide loading indicator
}

function notify(message, type = "info") {
    // Show notification
    const bg = type === "success" ? "var(--success)" : type === "error" ? "var(--error)" : "var(--primary)";
    console.log(`[${type.toUpperCase()}] ${message}`);
}

async function loadSettings() {
    try {
        const data = await API.get("/api/settings");
        document.getElementById("llmProvider").value = data.llm.provider || "ollama";
            document.getElementById("llmModel").value = data.llm.model || "llama2-code";
        document.getElementById("llmApiKey").value = data.llm.api_key || "";
        document.getElementById("llmEndpoint").value = data.llm.endpoint || "http://localhost:11434";
        document.getElementById("enableRag").checked = !!(data.rag && data.rag.enabled);
        state.skills = data.skills || [];
        state.extensions = data.extensions || [];
        renderSkillList();
        renderExtensionList();
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

async function saveSettings() {
    try {
        const llm = {
            provider: document.getElementById("llmProvider").value,
            model: document.getElementById("llmModel").value,
            api_key: document.getElementById("llmApiKey").value,
            endpoint: document.getElementById("llmEndpoint").value
        };
        const rag = {
            enabled: document.getElementById("enableRag").checked,
            sources: []
        };
        await API.post("/api/settings", { llm, rag, skills: state.skills, extensions: state.extensions });
        notify("Settings saved", "success");
        document.getElementById("settingsModal").classList.remove("active");
    } catch (e) {
        notify("Failed to save settings: " + e.message, "error");
        console.error(e);
    }
}

function renderSkillList() {
    const container = document.getElementById("skillList");
    if (!container) return;
    if (!state.skills || !state.skills.length) {
        container.innerHTML = "<div class='skill-empty'>No skills imported yet.</div>";
        return;
    }

    container.innerHTML = state.skills.map(skill => `
        <div class="skill-item">
            <div class="skill-title">${escapeHtml(skill.name)}</div>
            <div class="skill-meta">${escapeHtml(skill.description || "Imported skill")}</div>
            <button type="button" class="btn-secondary btn-small" onclick="deleteSkill('${encodeURIComponent(skill.name)}')">Remove</button>
        </div>
    `).join("");
}

function renderExtensionList() {
    const container = document.getElementById("extensionList");
    if (!container) return;
    if (!state.extensions || !state.extensions.length) {
        container.innerHTML = "<div class='skill-empty'>No extensions installed yet.</div>";
        return;
    }

    container.innerHTML = state.extensions.map(extension => `
        <div class="skill-item">
            <div class="skill-title">${escapeHtml(extension.name)}${extension.version ? ' @ ' + escapeHtml(extension.version) : ''}${extension.publisher ? ' (' + escapeHtml(extension.publisher) + ')' : ''}</div>
            <div class="skill-meta">${escapeHtml(extension.description || "Extension capability")}</div>
            <div class="skill-meta">Capabilities: ${escapeHtml((extension.capabilities || []).join(", "))}</div>
            <button type="button" class="btn-secondary btn-small" onclick="deleteExtension('${encodeURIComponent(extension.name)}')">Remove</button>
        </div>
    `).join("");
}

async function importSkill() {
    const name = prompt("Skill name:");
    if (!name) return;
    const description = prompt("Skill description (optional):", "");
    const content = prompt("Skill content or instructions:", "");
    if (!content) {
        notify("Skill content is required", "warning");
        return;
    }

    try {
        await API.post("/api/skills", { name, description, content });
        const response = await API.get("/api/skills");
        state.skills = response.skills || [];
        renderSkillList();
        notify("Skill imported", "success");
    } catch (e) {
        notify("Import failed: " + e.message, "error");
    }
}

async function importExtension() {
    const name = prompt("Extension name:");
    if (!name) return;
    const description = prompt("Extension description (optional):", "");
    const publisher = prompt("Extension publisher (optional):", "");
    const version = prompt("Extension version (optional):", "");
    const capabilitiesInput = prompt("Extension capabilities (comma separated, optional):", "");
    const manifestInput = prompt("Paste VS Code extension manifest JSON (optional):", "");

    const capabilities = capabilitiesInput
        ? capabilitiesInput.split(",").map(c => c.trim()).filter(Boolean)
        : [];

    let manifest = null;
    if (manifestInput) {
        try {
            manifest = JSON.parse(manifestInput);
        } catch (e) {
            notify("Invalid manifest JSON. Please paste valid JSON.", "error");
            return;
        }
    }

    try {
        await API.post("/api/extensions", { name, publisher, version, description, capabilities, manifest });
        const response = await API.get("/api/extensions");
        state.extensions = response.extensions || [];
        renderExtensionList();
        notify("Extension added", "success");
    } catch (e) {
        notify("Extension import failed: " + e.message, "error");
    }
}

async function deleteSkill(name) {
    const decoded = decodeURIComponent(name);
    if (!confirm(`Delete skill '${decoded}'?`)) return;
    try {
        await API.delete(`/api/skills/${name}`);
        state.skills = state.skills.filter(skill => skill.name !== decoded);
        renderSkillList();
        notify("Skill removed", "success");
    } catch (e) {
        notify("Delete failed: " + e.message, "error");
    }
}

async function deleteExtension(name) {
    const decoded = decodeURIComponent(name);
    if (!confirm(`Delete extension '${decoded}'?`)) return;
    try {
        await API.delete(`/api/extensions/${name}`);
        state.extensions = state.extensions.filter(ext => ext.name !== decoded);
        renderExtensionList();
        notify("Extension removed", "success");
    } catch (e) {
        notify("Delete failed: " + e.message, "error");
    }
}

function runCode() {
    if (!state.currentFile) {
        notify("No file open", "warning");
        return;
    }
    notify("Running code...", "info");
    // Implement code execution
}

// Keyboard shortcuts
function setupKeyboard() {
    document.addEventListener("keydown", (e) => {
        if (e.ctrlKey || e.metaKey) {
            if (e.key === "s") {
                e.preventDefault();
                saveCurrentFile();
            } else if (e.key === "Enter") {
                e.preventDefault();
                runCode();
            } else if (e.key.toLowerCase() === "p" && e.shiftKey) {
                e.preventDefault();
                openCommandPalette();
            }
        }
    });

    const paletteInput = document.getElementById("commandPaletteInput");
    if (paletteInput) {
        paletteInput.addEventListener("input", (e) => filterCommandPalette(e.target.value));
        paletteInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                const list = document.getElementById("commandPaletteList");
                const firstItem = list.querySelector(".command-item");
                if (firstItem) firstItem.click();
            }
        });
    }
}
