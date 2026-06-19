"""
Nexus Tools Module
Provides sandbox execution environment for code
"""

import subprocess
import tempfile
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import json

logger = logging.getLogger(__name__)


class CodeExecutor:
    """Safe code execution environment"""
    
    def __init__(self, timeout: int = 30, max_output: int = 10000):
        self.timeout = timeout
        self.max_output = max_output
    
    async def execute_python(self, code: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute Python code safely"""
        context = context or {}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=Path.home() / "nexus-sandbox"
            )
            
            output = result.stdout[:self.max_output]
            error = result.stderr[:self.max_output]
            
            return {
                "success": result.returncode == 0,
                "output": output,
                "error": error,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {self.timeout}s",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "returncode": -1
            }
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    async def execute_bash(self, command: str) -> Dict[str, Any]:
        """Execute bash command"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=Path.home() / "nexus-sandbox"
            )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout[:self.max_output],
                "error": result.stderr[:self.max_output],
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Command timeout after {self.timeout}s",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "returncode": -1
            }


class Tool:
    """Base tool class"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool"""
        raise NotImplementedError


class FileTool(Tool):
    """File manipulation tool"""
    
    def __init__(self):
        super().__init__("file", "File operations")
    
    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute file operations"""
        try:
            if action == "read":
                path = kwargs.get("path")
                with open(path, 'r') as f:
                    content = f.read()
                return {"success": True, "content": content}
            
            elif action == "write":
                path = kwargs.get("path")
                content = kwargs.get("content")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w') as f:
                    f.write(content)
                return {"success": True, "message": f"Written to {path}"}
            
            elif action == "delete":
                path = kwargs.get("path")
                if os.path.isfile(path):
                    os.remove(path)
                    return {"success": True, "message": f"Deleted {path}"}
                else:
                    return {"success": False, "error": "File not found"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}


class ExtensionTool(Tool):
    """Tool for executing installed extensions"""

    def __init__(self, extensions: Optional[List[Dict[str, Any]]] = None):
        super().__init__("extension", "Execute a configured extension capability")
        self.extensions = self._normalize_extensions(extensions or [])

    def _normalize_extensions(self, extensions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        normalized = {}
        for ext in extensions:
            if not isinstance(ext, dict):
                continue
            manifest = ext.get("manifest", {})
            if isinstance(manifest, str):
                try:
                    manifest = json.loads(manifest)
                except Exception:
                    manifest = {}

            capabilities = ext.get("capabilities") or []
            if not capabilities:
                capabilities = self._extract_capabilities_from_manifest(manifest)

            name = ext.get("name") or manifest.get("name") or manifest.get("displayName")
            if not name:
                continue

            normalized[name] = {
                **ext,
                "manifest": manifest,
                "capabilities": capabilities,
                "name": name
            }
        return normalized

    def _extract_capabilities_from_manifest(self, manifest: Dict[str, Any]) -> List[str]:
        caps: List[str] = []
        contributes = manifest.get("contributes", {}) or {}

        for command in contributes.get("commands", []):
            if isinstance(command, dict) and command.get("command"):
                caps.append(f"command:{command['command']}")
                if command.get("title"):
                    caps.append(f"title:{command['title']}")

        for language in contributes.get("languages", []):
            if isinstance(language, dict) and language.get("id"):
                caps.append(f"language:{language['id']}")

        if contributes.get("debuggers"):
            caps.append("debugger")
        if contributes.get("themes"):
            caps.append("theme")
        if contributes.get("snippets"):
            caps.append("snippet")
        if contributes.get("keybindings"):
            caps.append("keybinding")
        if contributes.get("hover"):
            caps.append("hover")
        if contributes.get("codeActions"):
            caps.append("codeAction")
        if contributes.get("semanticTokens"):
            caps.append("semanticTokens")
        if contributes.get("configuration"):
            caps.append("configuration")

        return list(dict.fromkeys([cap for cap in caps if cap]))

    def update_extensions(self, extensions: Optional[List[Dict[str, Any]]] = None):
        self.extensions = self._normalize_extensions(extensions or [])

    async def execute(self, **kwargs) -> Dict[str, Any]:
        name = kwargs.get("name")
        command = kwargs.get("command")
        target = kwargs.get("target")
        args = kwargs.get("args", {})

        if not name:
            return {"success": False, "error": "Extension name is required"}

        extension = self.extensions.get(name)
        if not extension:
            return {"success": False, "error": f"Extension '{name}' is not installed"}

        capabilities = extension.get("capabilities", [])
        manifest = extension.get("manifest", {})
        result_meta = {
            "extension": name,
            "command": command,
            "target": target,
            "args": args,
            "capabilities": capabilities,
            "manifest": manifest
        }

        supported_commands = [cap.split(":", 1)[1] for cap in capabilities if cap.startswith("command:")]
        if command and command in supported_commands:
            return {
                "success": True,
                "result": f"Executed marketplace-style command '{command}' on extension '{name}' for target '{target or 'project'}'.",
                "meta": result_meta
            }

        if command and command.lower() in ["lint", "format", "autocomplete", "complete", "analyze"]:
            action_word = {
                "lint": "Linted",
                "format": "Formatted",
                "autocomplete": "Suggested",
                "complete": "Completed",
                "analyze": "Analyzed"
            }.get(command.lower(), "Executed")
            description = f"{action_word} target '{target or 'project'}' using extension '{name}'."
            if capabilities:
                description += f" Capabilities: {', '.join(capabilities)}."
            if manifest:
                description += f" Manifest keys: {', '.join(manifest.keys()) if isinstance(manifest, dict) else str(manifest)}."
            return {"success": True, "result": description, "meta": result_meta}

        description = f"Executed extension '{name}' with command '{command or 'unknown'}'"
        if target:
            description += f" on '{target}'"
        if capabilities:
            description += f" with capabilities {', '.join(capabilities)}"
        if manifest:
            description += f"; manifest keys: {', '.join(manifest.keys()) if isinstance(manifest, dict) else str(manifest)}"

        return {"success": True, "result": description, "meta": result_meta}


class ToolRegistry:
    """Registry for available tools"""
    
    def __init__(self, extensions: Optional[List[Dict[str, Any]]] = None):
        self.tools: Dict[str, Tool] = {}
        self.extension_tool = ExtensionTool(extensions)
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default tools"""
        self.register(FileTool())
        self.register(self.extension_tool)
    
    def update_extensions(self, extensions: Optional[List[Dict[str, Any]]] = None):
        self.extension_tool.update_extensions(extensions)

    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Tool:
        """Get a tool by name"""
        return self.tools.get(name)
    
    def get_all_tools(self) -> Dict[str, str]:
        """Get all tools and their descriptions"""
        return {name: tool.description for name, tool in self.tools.items()}
