#!/usr/bin/env python3
"""
Nexus Code Agent - Main Entry Point
Production-ready AI code agent with multi-model LLM support
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.server import NexusServer
from core.config import load_config


async def main():
    """Main entry point for Nexus Code Agent"""
    try:
        # Load configuration
        config = load_config()
        logger.info(f"Nexus Code Agent v{config.get('version', '1.0.0')}")
        
        # Initialize server
        server = NexusServer(config)
        
        # Start server
        await server.start()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
