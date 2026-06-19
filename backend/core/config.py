"""
Nexus Configuration Module
Handles all configuration loading and management
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_config() -> Dict[str, Any]:
    """Load configuration from file or environment"""
    config_path = Path(__file__).parent.parent / "config" / "config.json"
    
    # Default configuration
    default_config = {
        "version": "1.0.0",
        "app_name": "Nexus Code Agent",
        "server": {
            "host": os.getenv("NEXUS_HOST", "0.0.0.0"),
            "port": int(os.getenv("NEXUS_PORT", 8000)),
            "debug": os.getenv("NEXUS_DEBUG", "false").lower() == "true"
        },
        "llm": {
            "provider": os.getenv("LLM_PROVIDER", "ollama"),
            "model": os.getenv("LLM_MODEL", "llama2-code"),
            "preferred_models": ["llama2-code", "mistral-code", "codegen-3b"],
            "timeout_seconds": int(os.getenv("LLM_TIMEOUT", 300)),
            "retries": int(os.getenv("LLM_RETRIES", 2)),
            "concurrency": int(os.getenv("LLM_CONCURRENCY", 2)),
            "api_key": os.getenv("LLM_API_KEY", ""),
            "endpoint": os.getenv("LLM_ENDPOINT", "http://localhost:11434")
        },
        "rag": {
            "enabled": False,
            "sources": []
        },
        "skills": [],
        "extensions": [],
        "storage": {
            "base_path": os.getenv("STORAGE_PATH", "./projects"),
            "max_project_size": 1000000000  # 1GB
        },
        "security": {
            "allowed_domains": ["localhost", "127.0.0.1"],
            "cors_enabled": True
        }
    }
    
    # Load from file if exists
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                default_config.update(file_config)
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
    
    return default_config


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a specific config value using dot notation"""
    config = load_config()
    keys = key.split('.')
    value = config
    
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
            if value is None:
                return default
        else:
            return default
    
    return value if value is not None else default


def update_config(updates: Dict[str, Any]) -> bool:
    """Update configuration file"""
    try:
        config_path = Path(__file__).parent.parent / "config" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing config
        config = load_config()
        
        # Deep update
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = deep_update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d
        
        config = deep_update(config, updates)
        
        # Save
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error updating config: {e}")
        return False
