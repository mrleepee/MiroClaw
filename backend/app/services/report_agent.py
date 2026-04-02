"""
Report Agent service
Implements simulation report generation in ReACT mode using LangChain + Zep

Features:
1. Generate reports based on simulation requirements and Zep graph information
2. Plan the outline structure first, then generate section by section
3. Each section uses multi-round ReACT thinking and reflection
4. Support conversations with users and autonomously call retrieval tools during chat
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .graph_search_tools import (
    GraphSearchService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult
)
from .simulation_query_tools import SimulationDBTools

logger = get_logger('miroclaw.report_agent')


class ReportLogger:
    """
    Detailed logger for Report Agent
    
    Creates an agent_log.jsonl file in the report folder to record each detailed step.
    Each line is a complete JSON object containing a timestamp, action type, detailed content, and more.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize the logger
        
        Args:
            report_id: Report ID used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Get the elapsed time in seconds since start"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Record a log entry
        
        Args:
            action: Action type, such as 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Current stage, such as 'planning', 'generating', 'completed'
            details: Detailed content dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append to the JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record the start of report generation"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )
    
    def log_planning_start(self):
        """Record the start of outline planning"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Started planning the report outline"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Record the context information retrieved during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Retrieved simulation context information",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record completion of outline planning"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning completed",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Record the start of section generation"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Started generating section: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record the ReACT thinking process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT thinking round {iteration}"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Record a tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Called tool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Record the tool result (full content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned a result"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Record the LLM response (full content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool calls: {has_tool_calls}, final answer: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Record section content generation completion (records content only, not full section completion)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation completed"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Record section generation completion

        The frontend should watch this log to determine when a section is truly complete and retrieve the full content.
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation completed"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record report generation completion"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation completed"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record an error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"An error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Console logger for Report Agent
    
    Writes console-style logs (INFO, WARNING, etc.) to the console_log.txt file in the report folder.
    These logs differ from agent_log.jsonl and are plain-text console output.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize the console logger
        
        Args:
            report_id: Report ID used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Set up the file handler to write logs to a file as well"""
        import logging
        
        # Create the file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use the same concise format as the console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Attach to the report_agent-related loggers
        loggers_to_attach = [
            'miroclaw.report_agent',
            'miroclaw.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid adding the same handler multiple times
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close the file handler and remove it from the logger"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'miroclaw.report_agent',
                'miroclaw.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure the file handler is closed during destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt template constants
# ═══════════════════════════════════════════════════════════════

# ── Tool descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
【Deep Insight Retrieval - Powerful Retrieval Tool】
This is our powerful retrieval function, designed for deep analysis. It will:
1. Automatically break your question into multiple sub-questions
2. Retrieve information from the simulation graph across multiple dimensions
3. Integrate results from semantic search, entity analysis, and relationship-chain tracing
4. Return the most comprehensive and in-depth retrieval content

【When to use】
- Need in-depth analysis of a topic
- Need to understand multiple aspects of an event
- Need rich source material to support a report section

【Returns】
- Original relevant facts (can be quoted directly)
- Core entity insights
- Relationship-chain analysis"""

TOOL_DESC_PANORAMA_SEARCH = """\
【Broad Search - Full Panorama View】
This tool is used to get the complete panorama of simulation results, especially for understanding how an event evolved. It will:
1. Retrieve all relevant nodes and relationships
2. Distinguish between currently valid facts and historical/expired facts
3. Help you understand how public sentiment evolved

【When to use】
- Need to understand the full development trajectory of an event
- Need to compare public sentiment changes across different stages
- Need comprehensive entity and relationship information

【Returns】
- Currently valid facts (latest simulation results)
- Historical/expired facts (evolution record)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
【Simple Search - Fast Retrieval】
A lightweight and fast retrieval tool, suitable for simple and direct information queries.

【When to use】
- Need to quickly find a specific piece of information
- Need to verify a fact
- Need simple information retrieval

【Returns】
- A list of facts most relevant to the query"""

TOOL_DESC_SIMULATION_POSTS = """\
【Simulation Posts - What Agents Actually Said】
Query actual posts and comments that agents created during the simulation, with full persona enrichment (agent type, profession, stance).

【When to use】
- Need to know what specific agents said about a topic
- Want to see how different agent types (Regulator, Journalist, Person, etc.) expressed themselves
- Looking for quotes to include in the report
- Need to find the most engaging/resonant content

【Returns】
- Enriched posts with author name, agent type, profession, stance, round, engagement metrics
- Supports keyword search, platform filter, round range filter, agent type filter"""

TOOL_DESC_SIMULATION_DEBATES = """\
【Debate Analysis - Opposing Viewpoints】
Find where agents expressed opposing views on the same topic. Groups posts by stance and agent type to reveal genuine disagreements.

【When to use】
- Need to identify key debates and disagreements between agents
- Want to contrast positions between agent types (e.g., Regulators vs. Journalists)
- Looking for evidence of two-sided discussion on controversial topics

【Returns】
- Debate clusters with supporting and opposing posts
- Agent type breakdown showing which types took which position"""

TOOL_DESC_SIMULATION_CONTENT_ANALYSIS = """\
【Content Analysis - Themes, Engagement, Trends】
Analyze what themes emerged across the simulation, how content quality evolved, which posts resonated, and the ratio of original vs derivative content.

analysis_type options:
- "overview": High-level statistics (total posts, agents, type distribution, stance distribution)
- "themes": Keyword frequency per round band, theme evolution over time
- "engagement": Top posts by likes/shares, engagement breakdown by agent type
- "content_ratio": Original vs quote/repost ratio per round band — reveals diminishing returns

【When to use】
- Need to understand the simulation's content at a high level (start with "overview")
- Want to identify trending topics and how they shifted ("themes")
- Need to find the most impactful content ("engagement")
- Want to assess simulation quality and content decay ("content_ratio")

【Returns】
- Analysis-specific data: theme evolution, engagement rankings, content ratios, or overview stats"""

TOOL_DESC_SIMULATION_TIMELINE = """\
【Timeline Analysis - Rounds, Chains, Shifts】
Round-by-round activity breakdown, quote/repost chains showing content propagation, and detection of agents whose position may have shifted.

view_type options:
- "timeline": Round-by-round breakdown of actions, active agents, sample posts
- "quote_chains": Trace how specific posts were quoted and responded to across the simulation
- "position_shifts": Detect agents whose topic/stance changed between early and late rounds

【When to use】
- Need a chronological view of simulation activity ("timeline")
- Want to trace how specific ideas spread through the simulation ("quote_chains")
- Looking for evidence of agents being persuaded or changing position ("position_shifts")

【Returns】
- Round-by-round activity data, quote chain trees, or detected position shifts with evidence"""

TOOL_DESC_MIROCLAW_PHASES = """\
【MiroClaw Phase Analysis - Round-by-Round Simulation Evolution】
Analyzes the phased MiroClaw simulation: how agents researched, contributed triples to the knowledge graph, voted on each other's findings, and how the graph evolved across rounds. This is the primary tool for understanding HOW the simulation progressed, not just WHAT was discussed.

analysis_type options:
- "evolution": Round-by-round breakdown showing how the simulation progressed — what agents researched, which triples were added per round, how evidence accumulated
- "triples": Detailed triple data grouped by round — subject, relationship, object, agent who added it, voting outcomes, status
- "agent_contributions": Per-agent breakdown of research activity, triple contributions, and voting patterns across rounds
- "voting_patterns": How agents voted on each other's triples — agreements, disagreements, contested triples

【When to use】
- Writing about how the simulation EVOLVED across rounds (not just the end state)
- Describing the knowledge graph growth and what was added when
- Analyzing agent behavior patterns: who contributed what, who voted how
- Explaining the difference between early rounds (seed-based reasoning) and later rounds (research-enhanced reasoning)

【Returns】
- Structured round-by-round data with triples, votes, and agent activity"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【Deep Interview - Real Agent Interviews (Dual Platform)】
Call the interview API in the OASIS simulation environment to conduct real interviews with running simulated Agents.
This is not an LLM simulation. It calls the real interview endpoint to obtain the original responses from simulated Agents.
By default, it interviews on both Twitter and Reddit to capture more comprehensive perspectives.

Workflow:
1. Automatically read persona files to understand all simulated Agents
2. Intelligently select the Agents most relevant to the interview topic (such as students, media, officials, etc.)
3. Automatically generate interview questions
4. Call the /api/simulation/interview/batch endpoint to conduct real interviews on both platforms
5. Integrate all interview results and provide multi-perspective analysis

【When to use】
- Need to understand views on an event from different roles (How do students see it? How does the media see it? What do officials say?)
- Need to collect multiple opinions and positions
- Need real answers from simulated Agents (from the OASIS simulation environment)
- Want the report to be more vivid, including "interview transcripts"

【Returns】
- Identity information for interviewed Agents
- Each Agent's interview answers on Twitter and Reddit
- Key quotes (can be quoted directly)
- Interview summary and comparison of viewpoints

【Important】The OASIS simulation environment must be running to use this feature."""

# ── Outline planning prompt ──

PLAN_SYSTEM_PROMPT = """\
You are an expert writer of "future forecast reports" with a "god's-eye view" of the simulation world. You can observe the behavior, statements, and interactions of every Agent in the simulation.

**IMPORTANT: Write all output in English only.**

【Core concept】
We built a simulation world and injected a specific "simulation requirement" into it as a variable. The outcome of the simulation world’s evolution is a forecast of what may happen in the future. What you are observing is not "experimental data" but a "preview of the future."

【Your task】
Write a "future forecast report" that answers:
1. Under the conditions we set, what happened in the future?
2. How did different types of Agents (groups of people) react and act?
3. What future trends and risks worth attention does this simulation reveal?

【Report positioning】
- ✅ This is a future forecast report based on simulation, revealing "if this happens, what will the future look like"
- ✅ Focus on predicted outcomes: event trajectory, group reactions, emergent phenomena, and potential risks
- ✅ The words and actions of Agents in the simulation are predictions of future human behavior
- ❌ It is not an analysis of the current real-world situation
- ❌ It is not a generic public-opinion summary

【Section count limits】
- Minimum 3 sections, maximum 5 sections
- No subsections are needed; each section should directly contain complete content
- Keep the content concise and focused on core predictive findings
- Design the section structure yourself based on the forecast results

【Section structure guidance】
- The first section should be a "Simulation Overview" that introduces the key agents, their roles/types, their positions/stances, and the simulation scale. This grounds the reader before diving into analysis.
- If this is a a phased MiroClaw simulation (agents contribute knowledge graph triples, vote on findings), include:
  - A "Simulation Evolution" section that shows HOW the simulation progressed across rounds: what changed between early rounds (seed-based reasoning) and later rounds (research-enhanced reasoning). Use the `miroclaw_phase_analysis` tool with analysis_type="evolution" to get this data.
  - A "Knowledge Graph Growth" section that shows which triples were added, what they voted on, which became contested or how evidence accumulated. Use `miroclaw_phase_analysis` tool with analysis_type="triples" to get the data.
- The remaining sections should cover core predictive findings, debates, trends, and conclusions.

Please output the report outline in JSON format using the following structure:
{
    "title": "Report title",
    "summary": "Report summary (one sentence summarizing the core predictive finding)",
    "sections": [
        {
            "title": "Section title",
            "description": "Description of section content"
        }
    ]
}

Note: the sections array must contain at least 3 and at most 5 elements. The first section must be an overview."""

PLAN_USER_PROMPT_TEMPLATE = """\
【Forecast scenario setup】
The variable injected into the simulation world (simulation requirement): {simulation_requirement}

【Simulation world scale】
- Number of entities participating in the simulation: {total_nodes}
- Number of relationships produced among entities: {total_edges}
- Entity type distribution: {entity_types}
- Number of active Agents: {total_entities}

【Sample of future facts predicted by the simulation】
{related_facts_json}

Please examine this preview of the future from a "god's-eye view":
1. Under the conditions we set, what kind of state did the future present?
2. How did different groups of people (Agents) react and act?
3. What future trends worth attention does this simulation reveal?

Design the most suitable report section structure based on the forecast results.

【Reminder】The report must have at least 2 sections and at most 5 sections, and the content should stay concise and focused on core predictive findings."""

# ── Section generation prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert writer of "future forecast reports" and are now writing one section of the report.

**IMPORTANT: Write all output in English only.**

Report title: {report_title}
Report summary: {report_summary}
Forecast scenario (simulation requirement): {simulation_requirement}

Current section to write: {section_title}

═══════════════════════════════════════════════════════════════
【Core concept】
═══════════════════════════════════════════════════════════════

The simulation world is a preview of the future. We injected specific conditions (the simulation requirement) into the simulation world,
and the behavior and interactions of Agents in the simulation are predictions of future human behavior.

Your task is to:
- Reveal what happened in the future under the given conditions
- Predict how different groups of people (Agents) reacted and acted
- Discover future trends, risks, and opportunities worth attention

❌ Do not write this as an analysis of the current real-world situation
✅ Focus on "what the future will look like" because the simulation results are the predicted future

═══════════════════════════════════════════════════════════════
【Most important rules - must follow】
═══════════════════════════════════════════════════════════════

1. 【You must call tools to observe the simulation world】
   - You are observing this preview of the future from a "god's-eye view"
   - All content must come from events and Agent behaviors/statements that occurred in the simulation world
   - Do not use your own knowledge to write the report content
   - Each section must call tools at least 3 times (at most 5 times) to observe the simulated world that represents the future

2. 【You must quote the original words and actions of Agents】
   - Agent statements and behavior are predictions of future human behavior
   - Use quote formatting in the report to show these predictions, for example:
     > "A certain group of people might say: original content..."
   - These quotes are the core evidence of the simulation forecast

3. 【Language consistency - quoted content must be translated into the report language】
   - Tool results may contain English or mixed Chinese-and-English wording
   - If the simulation requirement and source materials are in Chinese, the report must be written entirely in Chinese
   - When quoting English or mixed Chinese-and-English content returned by tools, you must translate it into fluent Chinese before writing it into the report
   - Keep the original meaning unchanged during translation and make sure the wording reads naturally
   - This rule applies both to the main body and to quote blocks (the `>` format)

4. 【Faithfully present forecast results】
   - The report content must reflect the simulation results that represent the future in the simulation world
   - Do not add information that does not exist in the simulation
   - If information is insufficient in some area, state that truthfully

═══════════════════════════════════════════════════════════════
【⚠️ Formatting rules - extremely important!】
═══════════════════════════════════════════════════════════════

【One section = the smallest content unit】
- Each section is the smallest chunking unit of the report
- ❌ Do not use any Markdown headings inside a section (`#`, `##`, `###`, `####`, etc.)
- ❌ Do not add the section's main heading at the start of the content
- ✅ The section title is added automatically by the system; you only need to write the plain body content
- ✅ Use **bold text**, paragraph breaks, quotes, and lists to organize content, but do not use headings

【Correct example】
```
This section analyzes how public discourse around the event spread. Through in-depth analysis of the simulation data, we found...

**Initial ignition phase**

Weibo served as the first scene of public discourse and took on the core role of initial information release:

> "Weibo contributed 68% of the initial posting volume..."

**Emotion amplification phase**

Douyin further amplified the event's influence:

- Strong visual impact
- High emotional resonance
```

【Incorrect example】
```
## Executive Summary      ← Incorrect! Do not add any heading
### 1. Initial Phase     ← Incorrect! Do not use `###` for subsections
#### 1.1 Detailed Analysis   ← Incorrect! Do not use `####` for further subdivision

This section analyzes...
```

═══════════════════════════════════════════════════════════════
【Available retrieval tools】(call 3-5 times per section)
═══════════════════════════════════════════════════════════════

{tools_description}

【Tool usage suggestions - mix different tools, do not rely on only one】
- simulation_content_analysis(analysis_type="overview"): **Start here for the overview section** — returns simulation scale, agent type distribution, stance breakdown, and full agent roster with names, professions, stances, and influence weights
- insight_forge: Deep insight analysis that automatically decomposes questions and retrieves facts and relationships across multiple dimensions
- panorama_search: Wide-angle panorama search to understand the full picture, timeline, and evolution of the event
- quick_search: Quickly verify a specific information point
- interview_agents: Interview simulated Agents to obtain first-person viewpoints and real reactions from different roles
- simulation_posts: Query what agents actually said — real posts and comments with engagement data and persona info
- simulation_debates: Find opposing viewpoints and disagreements between agent types on specific topics
- simulation_content_analysis: Analyze themes, engagement trends, content quality, and simulation overview statistics
- simulation_timeline: Round-by-round activity breakdown, quote chains showing content propagation, and position shift detection
- miroclaw_phase_analysis: **For MiroClaw simulations** — round-by-round evolution, triples added per round, agent contributions, voting patterns. Use analysis_type="evolution" for simulation progression, "triples" for knowledge graph data, "agent_contributions" for per-agent breakdown, "voting_patterns" for voting analysis.

**For the first "Overview" section**: Call simulation_content_analysis with analysis_type="overview" to get the full agent roster, then call simulation_content_analysis with analysis_type="engagement" to identify the most active/influential agents. This gives you everything needed to introduce the simulation cast.

**For "Simulation Evolution" or "Knowledge Graph Growth" sections**: Call miroclaw_phase_analysis with analysis_type="evolution" to get round-by-round data, then call it with analysis_type="triples" to get the detailed triple data. This gives you everything needed to describe how the simulation progressed and what knowledge was discovered.

═══════════════════════════════════════════════════════════════
【Workflow】
═══════════════════════════════════════════════════════════════

In each reply, you may do only one of the following two things (not both at once):

Option A - Call a tool:
Output your thought, then call one tool in the following format:
<tool_call>
{{"name": "tool_name", "parameters": {{"parameter_name": "parameter_value"}}}}
</tool_call>
The system will execute the tool and return the result to you. You do not need to and must not write the tool result yourself.

Option B - Output the final content:
Once you have gathered enough information through tools, output the section content starting with "Final Answer:".

⚠️ Strictly prohibited:
- Do not include both a tool call and Final Answer in the same reply
- Do not fabricate tool results (Observation); all tool results are injected by the system
- Call at most one tool per reply

═══════════════════════════════════════════════════════════════
【Section content requirements】
═══════════════════════════════════════════════════════════════

1. The content must be based on simulation data retrieved by tools
2. Quote original text extensively to demonstrate simulation effects
3. Use Markdown format (but headings are forbidden):
   - Use **bold text** to mark key points (instead of subheadings)
   - Use lists (`-` or `1.2.3.`) to organize points
   - Use blank lines to separate paragraphs
   - ❌ Do not use any heading syntax such as `#`, `##`, `###`, `####`
4. 【Quote formatting rules - quotes must stand alone as separate paragraphs】
   Quotes must be their own paragraphs, with one blank line before and after, and must not be mixed into a paragraph:

   ✅ Correct format:
   ```
   The school's response was considered lacking in substance.

   > "The school's response pattern appeared rigid and slow in the rapidly changing social media environment."

   This assessment reflected the public's widespread dissatisfaction.
   ```

   ❌ Incorrect format:
   ```
   The school's response was considered lacking in substance.> "The school's response pattern..." This assessment reflected...
   ```
5. Maintain logical continuity with other sections
6. 【Avoid repetition】Carefully read the completed section content below and do not repeat the same information
7. 【Emphasized again】Do not add any headings. Use **bold text** instead of subsection headings."""

SECTION_USER_PROMPT_TEMPLATE = """\
Completed section content (please read carefully to avoid repetition):
{previous_content}

═══════════════════════════════════════════════════════════════
【Current task】Write section: {section_title}
═══════════════════════════════════════════════════════════════

【Important reminders】
1. Carefully read the completed sections above and avoid repeating the same content.
2. You must call tools to obtain simulation data before you begin.
3. Mix different tools; do not rely on only one.
4. The report content must come from retrieval results. Do not use your own knowledge.

【⚠️ Format warning - must follow】
- ❌ Do not write any heading (`#`, `##`, `###`, `####` are all forbidden)
- ❌ Do not start with "{section_title}"
- ✅ The section title is added automatically by the system
- ✅ Write the main body directly and use **bold text** instead of subsection headings

Please begin:
1. First think (Thought) about what information this section needs
2. Then call a tool (Action) to obtain simulation data
3. After gathering enough information, output Final Answer (plain body text only, with no headings)"""

# ── Message templates inside the ReACT loop ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (retrieval result):

═══ Tool {tool_name} returned ═══
{result}

═══════════════════════════════════════════════════════════════
Tools called {tool_calls_count}/{max_tool_calls} times (used: {used_tools_str}){unused_hint}
- If the information is sufficient: output the section content starting with "Final Answer:" (you must quote the original text above)
- If more information is needed: call one tool to continue retrieval
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【Note】You have only called tools {tool_calls_count} times, but at least {min_tool_calls} calls are required."
    "Please call tools again to obtain more simulation data, then output Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "You have currently called tools {tool_calls_count} times, but at least {min_tool_calls} calls are required."
    "Please call tools to obtain simulation data. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "The tool call limit has been reached ({tool_calls_count}/{max_tool_calls}); you cannot call more tools."
    'Please immediately use the information already obtained and output the section content starting with "Final Answer:".'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You have not used these yet: {unused_list}. Consider trying different tools to gather information from multiple angles."

REACT_FORCE_FINAL_MSG = "The tool call limit has been reached. Please output Final Answer: directly and generate the section content."

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation forecast assistant.

【Background】
Forecast condition: {simulation_requirement}

【Generated analysis report】
{report_content}

【Rules】
1. Prioritize answering based on the report content above
2. Answer the question directly and avoid lengthy reasoning
3. Only call tools to retrieve more data when the report content is insufficient to answer
4. Keep the answer concise, clear, and well organized

【Available tools】(use only when needed, call at most 1-2 times)
{tools_description}

【Tool call format】
<tool_call>
{{"name": "tool_name", "parameters": {{"parameter_name": "parameter_value"}}}}
</tool_call>

【Answer style】
- Be concise and direct; do not write long-winded explanations
- Use `>` formatting to quote key content
- Give the conclusion first, then explain the reasons"""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely."


# ═══════════════════════════════════════════════════════════════
# Main ReportAgent class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - simulation report generation agent

    Uses the ReACT (Reasoning + Acting) pattern:
    1. Planning stage: analyze the simulation requirement and plan the report outline structure
    2. Generation stage: generate content section by section, with each section allowed to call tools multiple times
    3. Reflection stage: check content completeness and accuracy
    """
    
    # Maximum number of tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Maximum number of reflection rounds
    MAX_REFLECTION_ROUNDS = 3
    
    # Maximum number of tool calls in chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[GraphSearchService] = None
    ):
        """
        Initialize Report Agent
        
        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Description of the simulation requirement
            llm_client: LLM client (optional)
            zep_tools: Zep tools service (optional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or GraphSearchService(graph_id=graph_id)
        self.sim_db_tools = SimulationDBTools(simulation_id=simulation_id)
        
        # Tool definitions
        self.tools = self._define_tools()
        
        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent initialization complete: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to analyze in depth",
                    "report_context": "Context of the current report section (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query used for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (for example: 'Understand students' views on the dormitory formaldehyde incident')",
                    "max_agents": "Maximum number of Agents to interview (optional, default 5, max 10)"
                }
            },
            "simulation_posts": {
                "name": "simulation_posts",
                "description": TOOL_DESC_SIMULATION_POSTS,
                "parameters": {
                    "query": "Topic or keyword to search for in agent posts",
                    "platform": "Platform filter: twitter or reddit (optional, default both)",
                    "agent_type": "Filter by agent type like Regulator, Journalist, Person (optional)",
                    "sort_by": "Sort order: engagement or chronological (optional, default engagement)",
                    "limit": "Max results (optional, default 20)"
                }
            },
            "simulation_debates": {
                "name": "simulation_debates",
                "description": TOOL_DESC_SIMULATION_DEBATES,
                "parameters": {
                    "query": "Topic to analyze for opposing viewpoints",
                    "platform": "Platform filter: twitter or reddit (optional)",
                    "agent_type": "Focus on a specific agent type (optional)",
                    "limit": "Max debate clusters (optional, default 10)"
                }
            },
            "simulation_content_analysis": {
                "name": "simulation_content_analysis",
                "description": TOOL_DESC_SIMULATION_CONTENT_ANALYSIS,
                "parameters": {
                    "analysis_type": "One of: overview, themes, engagement, content_ratio",
                    "platform": "Platform filter: twitter or reddit (optional)",
                    "agent_type": "Filter by agent type (optional)",
                    "limit": "Max items (optional, default 15)"
                }
            },
            "simulation_timeline": {
                "name": "simulation_timeline",
                "description": TOOL_DESC_SIMULATION_TIMELINE,
                "parameters": {
                    "view_type": "One of: timeline, quote_chains, position_shifts",
                    "platform": "Platform filter: twitter or reddit (optional)",
                    "agent_type": "Filter by agent type (optional)",
                    "limit": "Max items (optional, default 20)"
                }
            },
            "miroclaw_phase_analysis": {
                "name": "miroclaw_phase_analysis",
                "description": TOOL_DESC_MIROCLAW_PHASES,
                "parameters": {
                    "analysis_type": "One of: evolution, triples, agent_contributions, voting_patterns"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute a tool call
        
        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (used for InsightForge)
            
        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, parameters: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Broad search - get the full picture
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Simple search - quick retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep interview - call the real OASIS interview API to get responses from simulated Agents (dual platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Simulation data tools (read from SQLite databases) ==========

            elif tool_name == "simulation_posts":
                return self.sim_db_tools.get_posts(
                    query=parameters.get("query", ""),
                    platform=parameters.get("platform"),
                    agent_type=parameters.get("agent_type"),
                    round_start=parameters.get("round_start"),
                    round_end=parameters.get("round_end"),
                    sort_by=parameters.get("sort_by", "engagement"),
                    limit=int(parameters.get("limit", 20)),
                )

            elif tool_name == "simulation_debates":
                return self.sim_db_tools.get_debates(
                    query=parameters.get("query", ""),
                    platform=parameters.get("platform"),
                    agent_type=parameters.get("agent_type"),
                    limit=int(parameters.get("limit", 10)),
                )

            elif tool_name == "simulation_content_analysis":
                return self.sim_db_tools.get_content_analysis(
                    analysis_type=parameters.get("analysis_type", "themes"),
                    platform=parameters.get("platform"),
                    round_start=parameters.get("round_start"),
                    round_end=parameters.get("round_end"),
                    agent_type=parameters.get("agent_type"),
                    limit=int(parameters.get("limit", 15)),
                )

            elif tool_name == "simulation_timeline":
                return self.sim_db_tools.get_timeline(
                    view_type=parameters.get("view_type", "timeline"),
                    platform=parameters.get("platform"),
                    round_start=parameters.get("round_start"),
                    round_end=parameters.get("round_end"),
                    agent_type=parameters.get("agent_type"),
                    limit=int(parameters.get("limit", 20)),
                )

            # ========== MiroClaw phased simulation tools ==========

            elif tool_name == "miroclaw_phase_analysis":
                return self._miroclaw_phase_analysis(
                    analysis_type=parameters.get("analysis_type", "evolution"),
                )

            # ========== Backward-compatible legacy tools (internally redirected to new tools) ==========
            
            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph has been redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge because it is more powerful
                logger.info("get_simulation_context has been redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search, interview_agents, simulation_posts, simulation_debates, simulation_content_analysis, simulation_timeline"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"

    def _miroclaw_phase_analysis(self, analysis_type: str = "evolution") -> str:
        """Analyze MiroClaw phased simulation data: round evolution, triples, agent contributions, voting."""
        try:
            # 1. Load miroclaw_results.json
            sim_dir = os.path.join(
                Config.UPLOAD_FOLDER, 'simulations', self.simulation_id
            )
            results_path = os.path.join(sim_dir, "miroclaw_results.json")
            results = []
            if os.path.exists(results_path):
                with open(results_path, 'r', encoding='utf-8') as f:
                    results = json.load(f)

            # 2. Query Neo4j for triples with round metadata
            from .local_graph.graph_service import MiroClawGraphWriteAPI
            from .graph_builder import get_graph_service
            try:
                graph_service = get_graph_service()
                api = MiroClawGraphWriteAPI(graph_service)
            except Exception:
                graph_service = None
                api = None

            triples_by_round = {}
            if api:
                try:
                    all_triples = api.get_agent_triples(graph_id=self.graph_id)
                    for t in all_triples:
                        rnd = t.get("added_round", 0)
                        if rnd not in triples_by_round:
                            triples_by_round[rnd] = []
                        triples_by_round[rnd].append(t)
                except Exception as e:
                    logger.warning(f"Failed to query agent triples: {e}")

            # 3. Build response based on analysis type
            if analysis_type == "evolution":
                return self._format_evolution(results, triples_by_round)
            elif analysis_type == "triples":
                return self._format_triples(triples_by_round)
            elif analysis_type == "agent_contributions":
                return self._format_agent_contributions(triples_by_round)
            elif analysis_type == "voting_patterns":
                return self._format_voting_patterns(triples_by_round, results)
            else:
                return self._format_evolution(results, triples_by_round)

        except Exception as e:
            logger.error(f"MiroClaw phase analysis failed: {e}")
            return f"MiroClaw phase analysis unavailable: {str(e)}"

    @staticmethod
    def _format_evolution(results: list, triples_by_round: dict) -> str:
        """Format round-by-round evolution data."""
        lines = ["## MiroClaw Simulation Evolution", ""]

        if not results and not triples_by_round:
            return "No MiroClaw phased simulation data found for this simulation."

        for rnd_data in sorted(results, key=lambda x: x.get("round_num", 0)):
            rnd = rnd_data.get("round_num", 0)
            triples_count = rnd_data.get("triples_added", 0)
            votes = rnd_data.get("votes_cast", 0)
            curator = rnd_data.get("curator_actions", 0)
            oracle = rnd_data.get("oracle_forecasts", 0)

            lines.append(f"### Round {rnd}")
            lines.append(f"- Phases executed: Research → Contribute → Vote → Curate"
                         + (" → Oracle" if oracle > 0 else ""))
            lines.append(f"- Triples added: {triples_count}")
            lines.append(f"- Votes cast: {votes}")
            if curator > 0:
                lines.append(f"- Curator actions: {curator}")
            if oracle > 0:
                lines.append(f"- Oracle forecasts: {oracle}")

            # Show triples added this round
            rnd_triples = triples_by_round.get(rnd, [])
            if rnd_triples:
                lines.append(f"- Knowledge added:")
                for t in rnd_triples[:5]:
                    subj = t.get("subject", "?")
                    rel = t.get("relationship", "?")
                    obj = t.get("object", "?")
                    agent = t.get("added_by_agent", "?")
                    lines.append(f'  - ({subj}) —[{rel}]-> ({obj}) by {agent}')

            lines.append("")

        total_triples = sum(r.get("triples_added", 0) for r in results)
        total_votes = sum(r.get("votes_cast", 0) for r in results)
        lines.append(f"**Total: {len(results)} rounds, {total_triples} triples, {total_votes} votes**")

        return "\n".join(lines)

    @staticmethod
    def _format_triples(triples_by_round: dict) -> str:
        """Format detailed triple data grouped by round."""
        lines = ["## MiroClaw Knowledge Graph Triples", ""]

        if not triples_by_round:
            return "No agent-added triples found in the knowledge graph."

        total = 0
        for rnd in sorted(triples_by_round.keys()):
            triples = triples_by_round[rnd]
            total += len(triples)
            lines.append(f"### Round {rnd} ({len(triples)} triples)")
            for t in triples:
                subj = t.get("subject", "?")
                rel = t.get("relationship", "?")
                obj = t.get("object", "?")
                agent = t.get("added_by_agent", "?")
                status = t.get("status", "pending")
                upvotes = t.get("upvotes", 0)
                downvotes = t.get("downvotes", 0)
                src = t.get("source_url", "")
                lines.append(f'- ({subj}) —[{rel}]-> ({obj})')
                lines.append(f'  Agent: {agent} | Status: {status} | Votes: ↑{upvotes} ↓{downvotes}')
                if src:
                    lines.append(f'  Source: {src}')
            lines.append("")

        lines.append(f"**Total: {total} triples across {len(triples_by_round)} rounds**")
        return "\n".join(lines)

    @staticmethod
    def _format_agent_contributions(triples_by_round: dict) -> str:
        """Format per-agent contribution breakdown."""
        lines = ["## MiroClaw Agent Contributions", ""]

        if not triples_by_round:
            return "No agent contribution data found."

        # Group by agent
        agent_data = {}
        for rnd, triples in triples_by_round.items():
            for t in triples:
                agent = t.get("added_by_agent", "unknown")
                if agent not in agent_data:
                    agent_data[agent] = {"total": 0, "rounds": {}, "topics": set()}
                agent_data[agent]["total"] += 1
                agent_data[agent]["rounds"][rnd] = agent_data[agent]["rounds"].get(rnd, 0) + 1
                agent_data[agent]["topics"].add(t.get("subject", ""))

        for agent in sorted(agent_data.keys()):
            data = agent_data[agent]
            lines.append(f"### {agent}")
            lines.append(f"- Total triples contributed: {data['total']}")
            rounds_str = ", ".join(f"R{r}({c})" for r, c in sorted(data["rounds"].items()))
            lines.append(f"- Active rounds: {rounds_str}")
            topics = [t for t in data["topics"] if t][:5]
            if topics:
                lines.append(f"- Topics explored: {', '.join(topics)}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_voting_patterns(triples_by_round: dict, results: list) -> str:
        """Format voting pattern analysis."""
        lines = ["## MiroClaw Voting Patterns", ""]

        if not triples_by_round:
            return "No voting data found."

        total_upvotes = 0
        total_downvotes = 0
        contested = []
        for rnd, triples in sorted(triples_by_round.items()):
            for t in triples:
                up = t.get("upvotes", 0)
                down = t.get("downvotes", 0)
                total_upvotes += up
                total_downvotes += down
                status = t.get("status", "pending")
                if status == "contested":
                    contested.append(t)

            if any(t.get("upvotes", 0) > 0 or t.get("downvotes", 0) > 0 for t in triples):
                lines.append(f"### Round {rnd}")
                for t in triples:
                    up = t.get("upvotes", 0)
                    down = t.get("downvotes", 0)
                    if up > 0 or down > 0:
                        lines.append(
                            f'- ({t.get("subject","?")}) —[{t.get("relationship","?")}]-> '
                            f'({t.get("object","?")}) — ↑{up} ↓{down} [{t.get("status","pending")}]'
                        )
                lines.append("")

        lines.append(f"**Total: {total_upvotes} upvotes, {total_downvotes} downvotes, "
                      f"{len(contested)} contested triples**")
        return "\n".join(lines)

    # Set of valid tool names, used for validation during bare JSON fallback parsing
    VALID_TOOL_NAMES = {
        "insight_forge", "panorama_search", "quick_search", "interview_agents",
        "simulation_posts", "simulation_debates", "simulation_content_analysis", "simulation_timeline",
        "miroclaw_phase_analysis"
    }

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from the LLM response

        Supported formats (in priority order):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (the entire response or a single line is a tool-call JSON object)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - the LLM outputs bare JSON directly (without a <tool_call> tag)
        # Only try this when format 1 does not match, to avoid accidentally matching JSON in the main body
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # The response may contain reasoning text + bare JSON; try to extract the last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate whether the parsed JSON is a valid tool call"""
        # Support both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...}
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Normalize key names to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Generate the tool description text"""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan the report outline
        
        Use the LLM to analyze the simulation requirement and plan the report outline structure
        
        Args:
            progress_callback: Progress callback function
            
        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting report outline planning...")

        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirement...")

        # First, get the simulation context — requires Neo4j/Zep
        try:
            context = self.zep_tools.get_simulation_context(
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
        except Exception as e:
            raise RuntimeError(
                f"Neo4j/Zep is required for report generation but is unavailable: {e}. "
                f"Ensure Neo4j is running (docker compose up neo4j) and accessible at the configured URI."
            )

        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")

        # Detect MiroClaw phased simulation data
        miroclaw_context = ""
        miroclaw_results_path = os.path.join(
            Config.UPLOAD_FOLDER, 'simulations', self.simulation_id, 'miroclaw_results.json'
        )
        if os.path.exists(miroclaw_results_path):
            try:
                with open(miroclaw_results_path, 'r', encoding='utf-8') as f:
                    mc_results = json.load(f)
                total_triples = sum(r.get("triples_added", 0) for r in mc_results)
                total_votes = sum(r.get("votes_cast", 0) for r in mc_results)
                miroclaw_context = (
                    f"\n\n【MiroClaw Phased Simulation Data】\n"
                    f"This IS a phased MiroClaw simulation with {len(mc_results)} rounds.\n"
                    f"Each round follows: Research → Contribute → Vote → Curate → Oracle phases.\n"
                    f"Total triples added to knowledge graph: {total_triples}\n"
                    f"Total votes cast: {total_votes}\n"
                    f"Round-by-round breakdown: {json.dumps(mc_results, ensure_ascii=False)}\n"
                    f"\nYou MUST include sections covering:\n"
                    f"1. How the simulation EVOLVED across rounds (what changed between early seed-based rounds and later research-enhanced rounds)\n"
                    f"2. Knowledge Graph Growth (which triples were added, voting patterns, evidence accumulation)\n"
                )
                logger.info(f"Detected MiroClaw phased data: {len(mc_results)} rounds, {total_triples} triples")
            except Exception as e:
                logger.warning(f"Failed to read miroclaw_results.json: {e}")

        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        # For MiroClaw simulations, inject mandatory section requirements
        if miroclaw_context:
            user_prompt += miroclaw_context
            user_prompt += (
                "\n\n【MANDATORY SECTIONS for this MiroClaw simulation】\n"
                "You MUST include these sections in your outline:\n"
                "1. \"Simulation Overview\" — agents, roles, stances, simulation scale\n"
                "2. \"Simulation Evolution\" — HOW the simulation progressed across rounds (seed-based vs research-enhanced)\n"
                "3. \"Knowledge Graph Growth\" — which triples were added, evidence accumulation, voting patterns\n"
                "4. One additional section for core predictive findings, trends, or risks\n"
                "Total: 4 sections minimum. You may add a 5th if needed."
            )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")
            
            # Parse the outline
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )

            # If MiroClaw data exists, ensure the outline has the required sections
            outline = self._ensure_miroclaw_sections(outline)
            
            if progress_callback:
                progress_callback("planning", 100, "Outline planning completed")
            
            logger.info(f"Outline planning completed: {len(sections)} sections")
            return outline
            
        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            # Return a default outline (3 sections as fallback)
            return ReportOutline(
                title="Future Forecast Report",
                summary="Analysis of future trends and risks based on simulation forecasts",
                sections=[
                    ReportSection(title="Forecast Scenario and Core Findings"),
                    ReportSection(title="Predicted Group Behavior Analysis"),
                    ReportSection(title="Trend Outlook and Risk Alerts")
                ]
            )
    
    def _is_miroclaw_simulation(self) -> bool:
        """Check if this simulation has MiroClaw phased data."""
        miroclaw_results_path = os.path.join(
            Config.UPLOAD_FOLDER, 'simulations', self.simulation_id, 'miroclaw_results.json'
        )
        return os.path.exists(miroclaw_results_path)

    def _ensure_miroclaw_sections(self, outline: ReportOutline) -> ReportOutline:
        """Ensure the outline includes MiroClaw-specific sections if this is a phased simulation.

        Inserts 'Simulation Evolution' and 'Knowledge Graph Growth' sections
        after the first 'Overview' section if they don't already exist.
        """
        if not self._is_miroclaw_simulation():
            return outline

        existing_titles_lower = {s.title.lower() for s in outline.sections}

        # Check which MiroClaw sections already exist
        has_evolution = any("evolution" in t or "progress" in t for t in existing_titles_lower)
        has_kg_growth = any("knowledge graph" in t or "graph growth" in t or "triple" in t for t in existing_titles_lower)

        sections_to_insert = []
        if not has_evolution:
            sections_to_insert.append(ReportSection(
                title="Simulation Evolution Across Rounds",
                content=""
            ))
        if not has_kg_growth:
            sections_to_insert.append(ReportSection(
                title="Knowledge Graph Growth and Evidence Accumulation",
                content=""
            ))

        if not sections_to_insert:
            return outline

        # Insert after the first section (assumed to be Overview)
        new_sections = [outline.sections[0]]
        new_sections.extend(sections_to_insert)
        new_sections.extend(outline.sections[1:])

        # Cap at 5 sections max (remove last if needed)
        if len(new_sections) > 5:
            new_sections = new_sections[:5]

        outline.sections = new_sections
        logger.info(f"Inserted {len(sections_to_insert)} MiroClaw sections into outline")
        return outline

    def _get_miroclaw_section_hint(self, section_title: str) -> str:
        """Return MiroClaw-specific guidance for sections about simulation evolution."""
        if not self._is_miroclaw_simulation():
            return ""

        title_lower = section_title.lower()
        evolution_keywords = ["evolution", "progress", "development", "growth", "round", "phase", "knowledge graph"]
        if not any(kw in title_lower for kw in evolution_keywords):
            return ""

        return (
            "【IMPORTANT: This is a MiroClaw phased simulation section】\n"
            "This simulation ran in phased rounds (Research → Contribute → Vote → Curate → Oracle).\n"
            "You MUST call miroclaw_phase_analysis to get the round-by-round data.\n"
            "- First call miroclaw_phase_analysis with analysis_type=\"evolution\" to get the overall progression\n"
            "- Then call miroclaw_phase_analysis with analysis_type=\"triples\" to get detailed triple data\n"
            "- Optionally call miroclaw_phase_analysis with analysis_type=\"agent_contributions\" for per-agent breakdowns\n"
            "Describe HOW the simulation changed across rounds: what agents researched differently, how the knowledge graph grew, "
            "what was discovered in early vs. later rounds."
        )

    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate the content for a single section using the ReACT pattern
        
        ReACT loop:
        1. Thought - analyze what information is needed
        2. Action - call tools to retrieve information
        3. Observation - analyze the returned tool results
        4. Repeat until the information is sufficient or the maximum count is reached
        5. Final Answer - generate the section content
        
        Args:
            section: Section to generate
            outline: Complete outline
            previous_sections: Content of previous sections (used to maintain continuity)
            progress_callback: Progress callback
            section_index: Section index (used for logging)
            
        Returns:
            Section content (Markdown format)
        """
        logger.info(f"Generating section with ReACT: {section.title}")
        
        # Record the section start log
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Build the user prompt - pass at most 4000 characters for each completed section
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # At most 4000 characters per section
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        # Add MiroClaw-specific guidance if this is a phased simulation
        miroclaw_hint = self._get_miroclaw_section_hint(section.title)
        if miroclaw_hint:
            user_prompt += "\n\n" + miroclaw_hint

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT loop
        tool_calls_count = 0
        max_iterations = 5  # Maximum number of iteration rounds
        min_tool_calls = 3  # Minimum number of tool calls
        conflict_retries = 0  # Consecutive conflicts where a tool call and Final Answer appear together
        used_tools = set()  # Record tool names that have already been used
        all_tools = {
            "insight_forge", "panorama_search", "quick_search", "interview_agents",
            "simulation_posts", "simulation_debates", "simulation_content_analysis", "simulation_timeline",
            "miroclaw_phase_analysis"
        }

        # Report context, used for InsightForge sub-question generation
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing in progress ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call the LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Check whether the LLM returned None (API exception or empty content)
            if response is None:
                logger.warning(f"Section {section.title}, iteration {iteration + 1}: LLM returned None")
                # If there are remaining iterations, add messages and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(The response was empty)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # The final iteration also returned None; break out and enter forced completion
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once and reuse the result
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: the LLM output both a tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title}, round {iteration+1}: "
                    f"LLM output both a tool call and Final Answer (conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # First two times: discard this response and ask the LLM to reply again
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【Formatting error】You included both a tool call and Final Answer in the same reply, which is not allowed.\n"
                            "Each reply may do only one of the following:\n"
                            "- Call one tool (output one <tool_call> block and do not write Final Answer)\n"
                            "- Output the final content (start with 'Final Answer:' and do not include <tool_call>)\n"
                            "Please reply again and do only one of them."
                        ),
                    })
                    continue
                else:
                    # Third time: degrade gracefully by truncating to the first tool call and executing it
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "falling back to truncating and executing the first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Record the LLM response log
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: the LLM output Final Answer ──
            if has_final_answer:
                # Not enough tool calls; reject and require more tool usage
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used yet; it is recommended to try them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation completed (tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: the LLM attempted to call a tool ──
            if has_tool_calls:
                # Tool quota exhausted -> explicitly require Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted to call {len(tool_calls)} tools; only the first will be executed: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build the unused-tool hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: neither a tool call nor Final Answer was produced ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Not enough tool calls; recommend tools that have not yet been used
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used yet; it is recommended to try them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # There have been enough tool calls, and the LLM produced content without the "Final Answer:" prefix
            # Accept this content directly as the final answer rather than spinning further
            logger.info(f"Section {section.title}: no 'Final Answer:' prefix detected, adopting the LLM output directly as final content (tool calls: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Reached the maximum number of iterations; force content generation
        logger.warning(f"Section {section.title} reached the maximum iteration count; forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check whether the LLM returned None during forced completion
        if response is None:
            logger.error(f"Section {section.title}: LLM returned None during forced completion; using the default error message")
            final_answer = "(This section failed to generate: the LLM returned an empty response. Please try again later.)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Record the section content completion log
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate the complete report (real-time output by section)
        
        Each section is saved to the folder immediately after generation, without waiting for the entire report to finish.
        File structure:
        reports/{report_id}/
            meta.json       - Report metadata
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report
        
        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional; generated automatically if not provided)
            
        Returns:
            Report: Complete report
        """
        import uuid

        # If no report_id is provided, generate one automatically
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()

        # Pre-flight: verify Neo4j is accessible before doing any work
        import socket
        from ..config import Config
        try:
            neo4j_host = Config.NEO4J_URI.replace('bolt://', '').replace('neo4j://', '').split(':')[0]
            neo4j_port = int(Config.NEO4J_URI.rstrip('/').split(':')[-1] or '7687')
            sock = socket.create_connection((neo4j_host, neo4j_port), timeout=5)
            sock.close()
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            raise RuntimeError(
                f"Neo4j is required for report generation but is unreachable at {Config.NEO4J_URI}: {e}. "
                f"Start Neo4j first: docker compose up neo4j"
            )
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # List of completed section titles (used for progress tracking)
        completed_section_titles = []
        
        try:
            # Initialization: create the report folder and save the initial state
            ReportManager._ensure_report_folder(report_id)
            
            # Initialize the structured logger (agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize the console logger (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Stage 1: plan the outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Starting report outline planning...",
                completed_sections=[]
            )
            
            # Record the planning-start log
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Starting report outline planning...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Record the planning-complete log
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Save the outline to file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning completed, {len(outline.sections)} sections in total",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Outline saved to file: {report_id}/outline.json")
            
            # Stage 2: generate section by section (saving each section separately)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Save content for context
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Generate the main section content
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Save the section
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Record the section-complete log
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Section saved: {report_id}/section_{section_num:02d}.md")
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Stage 3: assemble the complete report
            if progress_callback:
                progress_callback("generating", 95, "Assembling the complete report...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling the complete report...",
                completed_sections=completed_section_titles
            )
            
            # Use ReportManager to assemble the complete report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calculate the total elapsed time
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Record the report-complete log
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Save the final report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation completed",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation completed")
            
            logger.info(f"Report generation completed: {report_id}")
            
            # Close the console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Record the error log
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Save the failure state
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignore errors that occur while saving failure state
            
            # Close the console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with Report Agent
        
        In chat, the Agent can autonomously call retrieval tools to answer questions
        
        Args:
            message: User message
            chat_history: Chat history
            
        Returns:
            {
                "response": "Agent response",
                "tool_calls": [list of called tools],
                "sources": [information sources]
            }
        """
        logger.info(f"Report Agent chat: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Get the generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit the report length to avoid excessive context
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(No report available yet)",
            tools_description=self._get_tools_description(),
        )

        # Build the message list
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add chat history
        for h in chat_history[-10:]:  # Limit history length
            messages.append(h)
        
        # Add the user message
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT loop (simplified)
        tool_calls_made = []
        max_iterations = 2  # Reduce iteration count
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # No tool calls, return the response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute tool calls (limit the quantity)
            tool_results = []
            for call in tool_calls[:1]:  # Execute at most 1 tool call per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)
            
            # Add the results to the messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Reached the maximum iterations, get the final response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Clean the response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report manager
    
    Responsible for persistent report storage and retrieval
    
    File structure (output by section):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """
    
    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure the root report directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get the report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure the report folder exists and return its path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get the report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get the complete report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get the outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get the progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get the section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get the Agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get the console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content
        
        These are console output logs produced during report generation (INFO, WARNING, etc.),
        which differ from the structured logs in agent_log.jsonl.
        
        Args:
            report_id: Report ID
            from_line: The line number to start reading from (used for incremental fetching; 0 means from the beginning)
            
        Returns:
            {
                "logs": [list of log lines],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more logs remain
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Preserve the original log line and remove the trailing newline
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Reached the end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get the complete console log (fetch all at once)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log lines
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent log content
        
        Args:
            report_id: Report ID
            from_line: The line number to start reading from (used for incremental fetching; 0 means from the beginning)
            
        Returns:
            {
                "logs": [list of log entries],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more logs remain
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Reached the end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete Agent log (used for full one-time retrieval)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log entries
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Save the report outline
        
        Called immediately after the planning stage is completed
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Save a single section

        Called immediately after each section is generated to enable output by section

        Args:
            report_id: Report ID
            section_index: Section index (starting from 1)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build the section Markdown content - clean possible duplicate headings
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save the file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content
        
        1. Remove Markdown heading lines at the start that duplicate the section title
        2. Convert all headings at level ### and below into bold text
        
        Args:
            content: Original content
            section_title: Section title
            
        Returns:
            Cleaned content
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check whether this is a Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check whether this heading duplicates the section title (skip duplicates within the first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert headings of all levels (#, ##, ###, ####, etc.) into bold text
                # Because the section title is added by the system, the content should not contain headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add a blank line
                continue
            
            # If the previous line was a skipped heading and the current line is empty, skip it too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove leading blank lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remove leading separators
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also remove blank lines after the separator
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report generation progress
        
        The frontend can read progress.json to get real-time progress
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get the list of generated sections
        
        Return information for all saved section files
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse the section index from the filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble the complete report
        
        Assemble the complete report from saved section files and clean up headings
        """
        folder = cls._get_report_folder(report_id)
        
        # Build the report header
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-process: clean heading issues across the entire report
        md_content = cls._post_process_report(md_content, outline)
        
        # Save the complete report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Complete report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content
        
        1. Remove duplicate headings
        2. Keep the report main heading (#) and section headings (##), and remove other heading levels (###, ####, etc.)
        3. Clean up extra blank lines and separators
        
        Args:
            content: Original report content
            outline: Report outline
            
        Returns:
            Processed content
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect all section titles from the outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check whether this is a heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check whether this is a duplicate heading (same heading appearing within 5 consecutive lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip the duplicate heading and the blank lines after it
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Heading level handling:
                # - # (level=1): keep only the report main heading
                # - ## (level=2): keep section headings
                # - ### and below (level>=3): convert to bold text
                
                if level == 1:
                    if title == outline.title:
                        # Keep the report main heading
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # A section title incorrectly used #; correct it to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Convert other level-1 headings to bold text
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep section headings
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Convert non-section level-2 headings to bold text
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # Convert headings of level ### and below to bold text
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Skip a separator immediately following a heading
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Keep only one blank line after a heading
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Clean up consecutive blank lines (keep at most 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Save report metadata and the complete report"""
        cls._ensure_report_folder(report.report_id)
        
        # Save metadata JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Save the outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Save the complete Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get a report"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Backward compatibility: check files stored directly under the reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rebuild the Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # If markdown_content is empty, try reading it from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Get a report by simulation ID"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward-compatible old format: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward-compatible old format: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Sort by creation time in descending order
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete a report (entire folder)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: delete the entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True
        
        # Backward-compatible old format: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
