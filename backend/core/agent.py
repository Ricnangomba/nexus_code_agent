"""
Nexus Agent Module
Core AI agent logic for code generation and task execution
"""

import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from enum import Enum

from core.llm import Message, LLMFactory, LLMProvider
from core.tools import ToolRegistry, Tool

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent execution state"""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    DONE = "done"


class AgentAction:
    """Agent action"""
    
    def __init__(self, tool: str, input_data: Dict[str, Any]):
        self.tool = tool
        self.input_data = input_data


class Agent:
    """Base AI Agent"""
    
    def __init__(self, llm_provider: LLMProvider, tool_registry: ToolRegistry, config: Optional[Dict[str, Any]] = None):
        self.llm = llm_provider
        self.tools = tool_registry
        self.config = config or {}
        self.state = AgentState.IDLE
        self.memory: List[Dict[str, Any]] = []
        self.max_iterations = 10
    
    async def run(self, task: str, context: Dict[str, Any] = None) -> str:
        """Run agent on a task"""
        context = context or {}
        self.state = AgentState.THINKING
        self.memory = []
        
        # System prompt
        system_prompt = self._build_system_prompt()
        
        # Initial message
        messages = [
            Message("system", system_prompt),
            Message("user", task)
        ]
        
        # Add context if provided
        if context:
            context_msg = f"\nContext: {str(context)}"
            messages.append(Message("system", context_msg))
        
        result = ""
        iterations = 0
        
        while iterations < self.max_iterations and self.state != AgentState.DONE:
            iterations += 1
            
            # Get LLM response
            response = await self.llm.chat(messages)
            
            # Parse action or response
            action = self._parse_response(response)
            
            if action is None:
                # Final response
                self.state = AgentState.DONE
                result = response
                break
            else:
                # Execute action
                self.state = AgentState.ACTING
                observation = await self._execute_action(action)
                
                # Add to memory
                self.memory.append({
                    "iteration": iterations,
                    "action": action.tool,
                    "input": action.input_data,
                    "observation": observation
                })
                
                # Add to messages
                messages.append(Message("assistant", response))
                messages.append(Message("user", f"Observation: {observation}"))
                
                self.state = AgentState.THINKING
        
        self.state = AgentState.IDLE
        return result
    
    async def stream_run(self, task: str, context: Dict[str, Any] = None) -> AsyncGenerator[str, None]:
        """Run agent with streaming output"""
        context = context or {}
        self.state = AgentState.THINKING
        self.memory = []
        
        system_prompt = self._build_system_prompt()
        
        messages = [
            Message("system", system_prompt),
            Message("user", task)
        ]
        
        if context:
            context_msg = f"\nContext: {str(context)}"
            messages.append(Message("system", context_msg))
        
        iterations = 0
        
        while iterations < self.max_iterations and self.state != AgentState.DONE:
            iterations += 1
            
            # Stream LLM response
            response_text = ""
            async for chunk in self.llm.stream_chat(messages):
                response_text += chunk
                yield chunk
            
            # Parse action
            action = self._parse_response(response_text)
            
            if action is None:
                self.state = AgentState.DONE
                break
            else:
                self.state = AgentState.ACTING
                yield f"\n\n[Executing: {action.tool}]\n"
                
                observation = await self._execute_action(action)
                
                self.memory.append({
                    "iteration": iterations,
                    "action": action.tool,
                    "input": action.input_data,
                    "observation": observation
                })
                
                messages.append(Message("assistant", response_text))
                messages.append(Message("user", f"Observation: {observation}"))
                
                self.state = AgentState.THINKING
        
        self.state = AgentState.IDLE
    
    async def _execute_action(self, action: AgentAction) -> str:
        """Execute a tool action"""
        try:
            tool = self.tools.get_tool(action.tool)
            if not tool:
                return f"Error: Tool '{action.tool}' not found"
            
            result = await tool.execute(**action.input_data)
            return str(result)
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return f"Error: {str(e)}"
    
    def _parse_response(self, response: str) -> Optional[AgentAction]:
        """Parse LLM response for actions"""
        # Look for action markers in response
        if "Action:" in response and "Input:" in response:
            try:
                # Extract action and input
                action_start = response.index("Action:") + 7
                action_end = response.index("\n", action_start)
                action_name = response[action_start:action_end].strip()
                
                input_start = response.index("Input:", action_end) + 6
                input_end = response.index("\n", input_start) if "\n" in response[input_start:] else len(response)
                input_str = response[input_start:input_end].strip()
                
                # Parse input as dict
                import json
                try:
                    input_data = json.loads(input_str)
                except:
                    input_data = {"command": input_str}
                
                return AgentAction(action_name, input_data)
            except (ValueError, IndexError):
                return None
        
        return None
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for agent"""
        available_tools = self.tools.get_all_tools()
        tools_desc = "\n".join([f"- {name}: {desc}" for name, desc in available_tools.items()])

        skills = self.config.get("skills", []) if isinstance(self.config, dict) else []
        extensions = self.config.get("extensions", []) if isinstance(self.config, dict) else []
        rag_config = self.config.get("rag", {}) if isinstance(self.config, dict) else {}

        skills_desc = "None"
        if skills:
            skills_desc = "\n".join([f"- {skill.get('name')}:{' ' + skill.get('description','') if skill.get('description') else ''}" for skill in skills])

        extensions_desc = "None"
        if extensions:
            extensions_desc = "\n".join([
                f"- {ext.get('name')}:{' ' + ext.get('description','') if ext.get('description') else ''} Capabilities: {', '.join(ext.get('capabilities', []))}"
                for ext in extensions
            ])

        rag_enabled = rag_config.get("enabled", False)
        rag_sources = rag_config.get("sources", [])
        rag_desc = "RAG is disabled."
        if rag_enabled:
            rag_desc = "RAG is enabled. Use retrieval augmented generation from available sources when useful."
            if rag_sources:
                rag_desc += "\nSources:\n" + "\n".join([f"- {src}" for src in rag_sources])

        return f"""You are Nexus, an AI code agent. You can use the following tools:

{tools_desc}

Imported skills:
{skills_desc}

Installed extensions:
{extensions_desc}

RAG configuration:
{rag_desc}

When you need to use a tool, respond with:
Action: <tool_name>
Input: {{"key": "value"}}

If an imported skill specifically applies, prefer using that skill before suggesting custom logic.
If an extension provides a capability, use it in your reasoning and mention which extension is being used.
Always think step by step, explain your reasoning, and clarify your next action.
"""
    
    def get_memory(self) -> List[Dict[str, Any]]:
        """Get agent execution memory"""
        return self.memory
