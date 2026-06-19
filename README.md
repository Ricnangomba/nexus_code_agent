# Nexus Code Agent

An AI-powered code agent with full IDE capabilities, built with FastAPI and Monaco Editor.

## Features

- **AI-Powered Code Generation**: Generate code using various LLM providers (Ollama, OpenAI, Claude)
- **Full Code Editor**: Monaco Editor integration with syntax highlighting for 30+ languages
- **Project Management**: Create, organize, and manage multiple projects
- **Terminal Integration**: Built-in terminal for running code
- **Agent Mode**: Use AI agents for complex multi-step tasks
- **Real-time Streaming**: WebSocket-based streaming for instant feedback
- **File Management**: Browse, create, edit, and delete files
- **Responsive UI**: Modern dark-themed interface with responsive design

## Requirements

- Python 3.8+
- Node.js 16+ (optional, for frontend development)
- Ollama (for local LLM) or API key for OpenAI/Claude

## Installation

### Backend Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/nexus-agent.git
cd nexus-agent
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your settings
```

### Running the Server

Start the development server:
```bash
cd backend
python main.py
```

The server will be available at `http://localhost:8000`

Frontend will be served at `http://localhost:8000`

## Configuration

Edit `config/config.json` to customize:
- LLM provider and model
- Server host and port
- Storage location
- Security settings

### Deploying to Netlify
This repository includes a `netlify.toml` that publishes the static frontend from the `frontend/` directory.
The backend remains a FastAPI app and must be hosted separately for the frontend to call it.

By default, the frontend will be served from Netlify and should be configured to use your deployed backend endpoint via runtime settings.

### Using Ollama (Recommended for local development)

1. Install Ollama from https://ollama.ai
2. Run Ollama: `ollama serve`
3. Pull a model: `ollama pull llama2`
4. Update `config.json` with Ollama endpoint

### Using OpenAI

1. Get an API key from https://platform.openai.com/api-keys
2. Update `config/config.json`:
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "api_key": "your-api-key",
    "endpoint": "https://api.openai.com/v1"
  }
}
```

## Project Structure

```
nexus-agent/
├── backend/
│   ├── main.py                 # Entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py           # AI agent logic
│   │   ├── config.py          # Configuration management
│   │   ├── llm.py             # LLM provider integration
│   │   ├── project.py         # Project management
│   │   ├── server.py          # FastAPI server
│   │   └── tools.py           # Tool registry and execution
│   └── tools/                 # Custom tools
├── frontend/
│   ├── index.html             # Main HTML
│   ├── css/
│   │   └── styles.css         # Global styles
│   └── js/
│       └── app.js             # Frontend logic
├── config/
│   └── config.json            # Server configuration
├── projects/                  # User projects directory
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## API Endpoints

### Project Management
- `POST /api/projects` - Create project
- `GET /api/projects` - List projects
- `DELETE /api/projects/{name}` - Delete project
- `GET /api/projects/{name}/files` - Get file tree

### File Operations
- `POST /api/file/read` - Read file
- `POST /api/file/write` - Write file
- `POST /api/file/delete` - Delete file

### AI Chat
- `WebSocket /ws/chat` - Chat with AI
- `WebSocket /ws/agent` - Use agent mode

### Utilities
- `GET /api/status` - Server status
- `GET /api/tools` - Available tools
- `GET /metrics` - Prometheus metrics endpoint for LLM throughput, queue size and latency

## Production Readiness
- LLM requests are processed through a queue and worker pool to smooth burst traffic
- Ollama preferred coding models are probed on startup and the first available model is selected
- Prometheus metrics include request counts, error counts, latency sums/counts, and queue backlog size

## WebSocket Messages

### Chat Request
```json
{
  "message": "Generate a Python function to sort a list"
}
```

### Chat Response
```json
{
  "type": "chunk",
  "content": "def sort_list(items):"
}
```

### Agent Request
```json
{
  "task": "Create a new Python project with tests"
}
```

### Agent Response
```json
{
  "type": "step",
  "thought": "I need to create a new project",
  "action": "file",
  "action_input": {"action": "write", "path": "main.py", "content": "..."}
}
```

## Development

### Adding Custom Tools

Create a new tool in `backend/core/tools.py`:

```python
class MyTool(Tool):
    def __init__(self):
        super().__init__("my_tool", "Description of my tool")
    
    async def execute(self, **kwargs):
        # Your tool logic here
        return {"success": True, "result": "..."}

# Register it
registry = ToolRegistry()
registry.register(MyTool())
```

### Adding LLM Providers

Extend `LLMProvider` class in `backend/core/llm.py` and register in `LLMFactory`.

## Troubleshooting

### Port Already in Use
Change the port in `config/config.json` or set environment variable:
```bash
export NEXUS_PORT=8001
```

### Ollama Connection Error
Ensure Ollama is running:
```bash
ollama serve
```

### WebSocket Connection Failed
Check CORS settings in `config/config.json` and ensure WebSocket support is enabled.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/nexus-agent/issues
- Documentation: https://github.com/yourusername/nexus-agent/wiki

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Editor powered by [Monaco Editor](https://microsoft.github.io/monaco-editor/)
- Terminal via [xterm.js](https://xtermjs.org/)
- AI integration with [Ollama](https://ollama.ai) and [OpenAI](https://openai.com/)

---

**Version**: 1.0.0  
**Last Updated**: June 2026
