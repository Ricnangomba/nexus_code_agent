"""
Nexus Server Module
FastAPI server for Nexus Code Agent
"""

import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from core.config import load_config, update_config
from core.llm import LLMFactory, QueuedBatchLLM, get_prometheus_metrics
from core.tools import ToolRegistry
from core.project import ProjectManager
from core.agent import Agent
import aiohttp

logger = logging.getLogger(__name__)


class SettingsUpdate(BaseModel):
    llm: Dict[str, Any]
    rag: Dict[str, Any] = {}
    skills: Optional[List[Dict[str, Any]]] = []
    extensions: Optional[List[Dict[str, Any]]] = []


class SkillItem(BaseModel):
    name: str
    description: Optional[str] = ""
    content: str


class ExtensionItem(BaseModel):
    name: str
    publisher: Optional[str] = ""
    version: Optional[str] = ""
    description: Optional[str] = ""
    capabilities: Optional[List[str]] = []
    manifest: Optional[Dict[str, Any]] = None


class NexusServer:
    """Nexus API Server"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = FastAPI(
            title="Nexus Code Agent",
            description="AI-powered code agent",
            version="1.0.0"
        )
        
        # Initialize components
        self.project_manager = ProjectManager(config["storage"]["base_path"])
        self.tool_registry = ToolRegistry(config.get("extensions", []))
        
        # Mount frontend static assets if available
        frontend_path = Path(__file__).parent.parent.parent / "frontend"
        if frontend_path.exists():
            self.app.mount("/static", StaticFiles(directory=str(frontend_path), html=False), name="static")
            self.frontend_index = frontend_path / "index.html"

        # Initialize LLM
        self.llm = self._create_llm_provider(config)
        # Wrap provider with queue-based workers to smooth load
        concurrency = config.get("llm", {}).get("concurrency", 2)
        try:
            self.llm = QueuedBatchLLM(self.llm, concurrency=concurrency)
        except Exception:
            pass
        self.agent = Agent(self.llm, self.tool_registry, config=self.config)

        # Register startup/shutdown handlers
        try:
            self.app.add_event_handler("startup", self._startup)
            self.app.add_event_handler("shutdown", self._shutdown)
        except Exception:
            pass
        
        # Setup routes
        self._setup_routes()
        self._setup_middleware()
    
    def _setup_middleware(self):
        """Setup CORS and other middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "ok", "app": "Nexus Code Agent"}
        
        @self.app.get("/api/status")
        async def status():
            return {
                "status": "running",
                "version": self.config.get("version", "1.0.0"),
                "llm": {
                    "provider": self.config["llm"]["provider"],
                    "model": self.config["llm"]["model"]
                }
            }
        
        @self.app.get("/api/tools")
        async def list_tools():
            return {"tools": self.tool_registry.get_all_tools()}

        @self.app.get("/metrics")
        async def metrics():
            return PlainTextResponse(get_prometheus_metrics(), media_type="text/plain")

        @self.app.get("/api/settings")
        async def get_settings():
            cfg = load_config()
            return {
                "llm": cfg.get("llm", {}),
                "rag": cfg.get("rag", {}),
                "skills": cfg.get("skills", []),
                "extensions": cfg.get("extensions", [])
            }

        @self.app.post("/api/settings")
        async def update_settings(settings: SettingsUpdate):
            if update_config({
                "llm": settings.llm,
                "rag": settings.rag,
                "skills": settings.skills or [],
                "extensions": settings.extensions or []
            }):
                self.config = load_config()
                self._refresh_provider()
                return {"success": True}
            raise HTTPException(status_code=500, detail="Could not update settings")

        @self.app.get("/api/skills")
        async def list_skills():
            cfg = load_config()
            return {"skills": cfg.get("skills", [])}

        @self.app.post("/api/skills")
        async def import_skill(skill: SkillItem):
            cfg = load_config()
            skills = cfg.get("skills", []) or []
            skills = [s for s in skills if s.get("name") != skill.name]
            skills.append(skill.dict())
            if update_config({"skills": skills}):
                self.config = load_config()
                self._refresh_provider()
                return {"success": True, "skills": skills}
            raise HTTPException(status_code=500, detail="Could not import skill")

        @self.app.delete("/api/skills/{skill_name}")
        async def delete_skill(skill_name: str):
            cfg = load_config()
            skills = cfg.get("skills", []) or []
            new_skills = [s for s in skills if s.get("name") != skill_name]
            if len(new_skills) == len(skills):
                raise HTTPException(status_code=404, detail="Skill not found")
            if update_config({"skills": new_skills}):
                self.config = load_config()
                self._refresh_provider()
                return {"success": True}
            raise HTTPException(status_code=500, detail="Could not delete skill")

        @self.app.get("/api/extensions")
        async def list_extensions():
            cfg = load_config()
            return {"extensions": cfg.get("extensions", [])}

        @self.app.post("/api/extensions")
        async def import_extension(extension: ExtensionItem):
            cfg = load_config()
            extensions = cfg.get("extensions", []) or []
            extensions = [e for e in extensions if e.get("name") != extension.name]
            extensions.append(extension.dict())
            if update_config({"extensions": extensions}):
                self.config = load_config()
                self._refresh_provider()
                return {"success": True, "extensions": extensions}
            raise HTTPException(status_code=500, detail="Could not import extension")

        @self.app.delete("/api/extensions/{extension_name}")
        async def delete_extension(extension_name: str):
            cfg = load_config()
            extensions = cfg.get("extensions", []) or []
            new_extensions = [e for e in extensions if e.get("name") != extension_name]
            if len(new_extensions) == len(extensions):
                raise HTTPException(status_code=404, detail="Extension not found")
            if update_config({"extensions": new_extensions}):
                self.config = load_config()
                self._refresh_provider()
                return {"success": True}
            raise HTTPException(status_code=500, detail="Could not delete extension")

        # Project endpoints
        @self.app.post("/api/projects")
        async def create_project(name: str, template: str = "blank", description: str = ""):
            result = self.project_manager.create_project(name, template, description)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.get("/api/projects")
        async def list_projects():
            result = self.project_manager.list_projects()
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.delete("/api/projects/{project_name}")
        async def delete_project(project_name: str):
            result = self.project_manager.delete_project(project_name)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.get("/api/projects/{project_name}/files")
        async def get_project_files(project_name: str):
            result = self.project_manager.get_file_tree(project_name)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.post("/api/file/read")
        async def read_file(project: str, path: str):
            result = self.project_manager.read_file(project, path)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.post("/api/file/write")
        async def write_file(project: str, path: str, content: str):
            result = self.project_manager.write_file(project, path, content)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.post("/api/file/delete")
        async def delete_file(project: str, path: str):
            result = self.project_manager.delete_file(project, path)
            if result["success"]:
                return result
            raise HTTPException(status_code=400, detail=result["error"])
        
        @self.app.get("/")
        async def root():
            if hasattr(self, "frontend_index") and self.frontend_index.exists():
                return FileResponse(self.frontend_index)
            raise HTTPException(status_code=404, detail="Frontend not found")
        
        # WebSocket endpoints
        @self.app.websocket("/ws/chat")
        async def websocket_chat(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_json()
                    message = data.get("message", "")
                    
                    # Stream response
                    async for chunk in self.agent.stream_run(message):
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk
                        })
                    
                    await websocket.send_json({"type": "done"})
            
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
            finally:
                await websocket.close()
        
        @self.app.websocket("/ws/agent")
        async def websocket_agent(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_json()
                    task = data.get("task", "")
                    
                    # Run agent and send steps
                    async for chunk in self.agent.stream_run(task):
                        await websocket.send_json({
                            "type": "step",
                            "content": chunk
                        })
                    
                    await websocket.send_json({"type": "done"})
            
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
            finally:
                await websocket.close()
    
    def _create_llm_provider(self, config: Dict[str, Any]):
        llm_config = config["llm"]
        provider = llm_config.get("provider", "ollama")
        model = llm_config.get("model")

        # If Ollama provider and model looks generic or unset, prefer configured coding models
        if provider == "ollama":
            preferred = llm_config.get("preferred_models") or []
            if (not model) or (model in ["llama2", "default", ""]):
                if preferred:
                    model = preferred[0]

        timeout_seconds = llm_config.get("timeout_seconds")
        retries = llm_config.get("retries")

        return LLMFactory.create(
            provider,
            endpoint=llm_config.get("endpoint"),
            api_key=llm_config.get("api_key"),
            model=model,
            timeout_seconds=timeout_seconds,
            retries=retries
        )

    def _refresh_provider(self):
        self.llm = self._create_llm_provider(self.config)
        # Ensure queue-based wrapper is preserved if the provider is reloaded
        concurrency = self.config.get("llm", {}).get("concurrency", 2)
        try:
            self.llm = QueuedBatchLLM(self.llm, concurrency=concurrency)
        except Exception:
            pass
        self.agent.llm = self.llm
        self.agent.config = self.config
        self.tool_registry.update_extensions(self.config.get("extensions", []))

    async def _startup(self):
        """Startup tasks: probe preferred models and refresh provider if needed"""
        try:
            await self._probe_models()
        except Exception:
            logger.exception("Model probing failed")

    async def _probe_models(self):
        llm_cfg = self.config.get("llm", {})
        provider = llm_cfg.get("provider")
        if provider != "ollama":
            return

        endpoint = llm_cfg.get("endpoint")
        preferred = llm_cfg.get("preferred_models", []) or []
        if not preferred or not endpoint:
            return

        async with aiohttp.ClientSession() as session:
            # Try models list endpoint first
            for model in preferred:
                try:
                    # Try a lightweight probe: call /api/models if available
                    models_url = f"{endpoint.rstrip('/')}/api/models"
                    resp = await session.get(models_url, timeout=5)
                    if resp.status == 200:
                        data = await resp.json()
                        available = []
                        if isinstance(data, dict) and data.get("models"):
                            available = data.get("models")
                        elif isinstance(data, list):
                            available = data
                        if model in available:
                            # select this model
                            logger.info(f"Probed and selected model {model}")
                            self.config["llm"]["model"] = model
                            self._refresh_provider()
                            return
                except Exception:
                    # fallback: try chat probe
                    try:
                        probe_payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "stream": False}
                        probe_url = f"{endpoint.rstrip('/')}/api/chat"
                        p_resp = await session.post(probe_url, json=probe_payload, timeout=5)
                        if p_resp.status == 200:
                            logger.info(f"Probed and selected model {model} via chat probe")
                            self.config["llm"]["model"] = model
                            self._refresh_provider()
                            return
                    except Exception:
                        continue

    async def _shutdown(self):
        """Cleanup provider resources on server shutdown"""
        try:
            if hasattr(self.llm, "close"):
                await self.llm.close()
        except Exception:
            logger.exception("Error closing LLM provider")

    async def start(self):
        """Start the server"""
        import uvicorn
        
        config = self.config["server"]
        logger.info(f"Starting Nexus Server on {config['host']}:{config['port']}")
        
        server = uvicorn.Server(uvicorn.Config(
            self.app,
            host=config["host"],
            port=config["port"],
            reload=config.get("debug", False)
        ))
        
        await server.serve()
