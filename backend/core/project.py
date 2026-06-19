"""
Nexus Project Module
Handles project management and file operations
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProjectConfig:
    """Project configuration"""
    name: str
    template: str
    description: str
    created_at: str
    language: str


class ProjectManager:
    """Manage projects and files"""
    
    def __init__(self, base_path: str = "./projects"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def create_project(self, name: str, template: str = "blank", description: str = "") -> Dict[str, Any]:
        """Create a new project"""
        try:
            project_path = self.base_path / name
            
            if project_path.exists():
                return {"success": False, "error": "Project already exists"}
            
            project_path.mkdir(parents=True, exist_ok=True)
            
            # Create project structure
            (project_path / "src").mkdir(exist_ok=True)
            (project_path / "tests").mkdir(exist_ok=True)
            
            # Create project config
            config = {
                "name": name,
                "template": template,
                "description": description,
                "created_at": str(Path.ctime(project_path)),
                "language": self._get_language_for_template(template)
            }
            
            config_file = project_path / "project.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Create template-specific files
            self._create_template_files(project_path, template)
            
            logger.info(f"Created project: {name}")
            return {"success": True, "path": str(project_path), "config": config}
        
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_project(self, name: str) -> Dict[str, Any]:
        """Delete a project"""
        try:
            project_path = self.base_path / name
            
            if not project_path.exists():
                return {"success": False, "error": "Project not found"}
            
            shutil.rmtree(project_path)
            logger.info(f"Deleted project: {name}")
            return {"success": True}
        
        except Exception as e:
            logger.error(f"Error deleting project: {e}")
            return {"success": False, "error": str(e)}
    
    def list_projects(self) -> Dict[str, Any]:
        """List all projects"""
        try:
            projects = []
            for project_dir in self.base_path.iterdir():
                if project_dir.is_dir():
                    config_file = project_dir / "project.json"
                    if config_file.exists():
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                            projects.append(config)
            
            return {"success": True, "projects": projects}
        
        except Exception as e:
            logger.error(f"Error listing projects: {e}")
            return {"success": False, "error": str(e)}
    
    def get_file_tree(self, project_name: str) -> Dict[str, Any]:
        """Get file tree for project"""
        try:
            project_path = self.base_path / project_name
            
            if not project_path.exists():
                return {"success": False, "error": "Project not found"}
            
            tree = self._build_tree(project_path)
            return {"success": True, "tree": tree}
        
        except Exception as e:
            logger.error(f"Error getting file tree: {e}")
            return {"success": False, "error": str(e)}
    
    def read_file(self, project_name: str, file_path: str) -> Dict[str, Any]:
        """Read file content"""
        try:
            full_path = self.base_path / project_name / file_path
            
            # Security check
            if not str(full_path.resolve()).startswith(str((self.base_path / project_name).resolve())):
                return {"success": False, "error": "Invalid path"}
            
            if not full_path.exists():
                return {"success": False, "error": "File not found"}
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            return {"success": True, "content": content}
        
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {"success": False, "error": str(e)}
    
    def write_file(self, project_name: str, file_path: str, content: str) -> Dict[str, Any]:
        """Write file content"""
        try:
            full_path = self.base_path / project_name / file_path
            
            # Security check
            if not str(full_path.resolve()).startswith(str((self.base_path / project_name).resolve())):
                return {"success": False, "error": "Invalid path"}
            
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Wrote file: {project_name}/{file_path}")
            return {"success": True}
        
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_file(self, project_name: str, file_path: str) -> Dict[str, Any]:
        """Delete a file"""
        try:
            full_path = self.base_path / project_name / file_path
            
            # Security check
            if not str(full_path.resolve()).startswith(str((self.base_path / project_name).resolve())):
                return {"success": False, "error": "Invalid path"}
            
            if full_path.exists():
                full_path.unlink()
                logger.info(f"Deleted file: {project_name}/{file_path}")
                return {"success": True}
            else:
                return {"success": False, "error": "File not found"}
        
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return {"success": False, "error": str(e)}
    
    def _build_tree(self, path: Path, prefix: str = "") -> Dict[str, Any]:
        """Build directory tree recursively"""
        tree = {
            "name": path.name,
            "type": "directory" if path.is_dir() else "file",
            "children": []
        }
        
        if path.is_dir():
            try:
                for item in sorted(path.iterdir()):
                    if not item.name.startswith('.'):
                        tree["children"].append(self._build_tree(item, prefix + "  "))
            except PermissionError:
                pass
        
        return tree
    
    def _get_language_for_template(self, template: str) -> str:
        """Get primary language for template"""
        languages = {
            "python": "python",
            "react": "javascript",
            "node": "javascript",
            "html": "html",
            "flask": "python",
            "blank": "text"
        }
        return languages.get(template, "text")
    
    def _create_template_files(self, project_path: Path, template: str):
        """Create template-specific files"""
        if template == "python":
            self._create_python_template(project_path)
        elif template == "react":
            self._create_react_template(project_path)
        elif template == "node":
            self._create_node_template(project_path)
        elif template == "html":
            self._create_html_template(project_path)
    
    def _create_python_template(self, project_path: Path):
        """Create Python project template"""
        (project_path / "src" / "main.py").write_text("#!/usr/bin/env python3\n\nprint('Hello from Nexus!')\n")
        (project_path / "requirements.txt").write_text("# Add dependencies here\n")
    
    def _create_react_template(self, project_path: Path):
        """Create React project template"""
        (project_path / "src" / "App.jsx").write_text("export default function App() {\n  return <h1>Welcome to Nexus</h1>;\n}\n")
        (project_path / "package.json").write_text(json.dumps({"name": "nexus-app", "version": "1.0.0"}, indent=2) + "\n")
    
    def _create_node_template(self, project_path: Path):
        """Create Node.js project template"""
        (project_path / "src" / "index.js").write_text("console.log('Hello from Nexus!');\n")
        (project_path / "package.json").write_text(json.dumps({"name": "nexus-app", "version": "1.0.0", "main": "src/index.js"}, indent=2) + "\n")
    
    def _create_html_template(self, project_path: Path):
        """Create HTML project template"""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nexus Project</title>
</head>
<body>
    <h1>Welcome to Nexus</h1>
    <p>Your HTML project is ready!</p>
</body>
</html>
"""
        (project_path / "src" / "index.html").write_text(html_content)
