import operator
from typing import Annotated, List, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

try:
    from langchain.agents import create_agent as _create_agent
except ImportError:
    from langgraph.prebuilt import create_react_agent as _create_agent

def build_agent(llm, tools, prompt):
    try:
        return _create_agent(llm, tools=tools, system_prompt=prompt)
    except TypeError:
        # fallback for older API
        return _create_agent(llm, tools, prompt=prompt)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END, START

from tools import (
    tavily_search_research,
    tavily_map_site,
    tavily_crawl_summary,
    tavily_extract_content,
)
from database import db_handler

# Use cheaper model for workers
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_smart = ChatOpenAI(model="gpt-4o", temperature=0)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str
    session_id: str

# Scout agent - finds URLs and site structure
scout_agent = build_agent(
    llm_fast,
    [tavily_search_research, tavily_map_site, tavily_crawl_summary],
    """You are a Recon Scout specializing in discovering and mapping relevant sources for market intelligence research.

Your role:
- Use tavily_search_research to find relevant URLs and initial information about the topic
- Use tavily_map_site to discover the structure of target websites (pricing pages, feature pages, etc.)
- Use tavily_crawl_summary to get overviews and summaries of key pages
- Identify the most relevant URLs that should be analyzed in detail

When reporting your findings:
- Clearly list the URLs you've discovered
- Indicate which URLs are most relevant for detailed extraction
- Provide context about what each URL contains (e.g., "pricing page", "feature comparison", "documentation")
- Help the Analyst know which URLs to extract detailed content from"""
)

# Analyst agent - extracts detailed content from specific URLs
analyst_agent = build_agent(
    llm_fast,
    [tavily_extract_content],
    """You are a Data Analyst specializing in extracting detailed, structured content from specific URLs.

Your role:
- Extract raw text content from URLs that the Scout has identified as relevant
- Focus on extracting specific details like: pricing information, feature lists, product specifications, comparison tables, documentation, etc.
- Use tavily_extract_content with comma-separated URLs when you need the full raw content from specific pages
- Provide structured summaries of the extracted content that directly answer the user's query

When extracting:
- Identify the most relevant URLs from the Scout's findings
- Extract content that provides concrete details, not just summaries
- Focus on factual information that can be used for competitive analysis"""
)
def scout_node(state: AgentState):
    result = scout_agent.invoke(state)
    output = result["messages"][-1]
    db_handler.log_step(state.get("session_id"), "Scout", "Research", output.content)
    return {"messages": [output]}

def analyst_node(state: AgentState):
    result = analyst_agent.invoke(state)
    output = result["messages"][-1]
    db_handler.log_step(state.get("session_id"), "Analyst", "Extraction", output.content)
    return {"messages": [output]}

# Supervisor routes between agents
members = ["Scout", "Analyst"]
options = ["FINISH"] + members

supervisor_prompt = (
    "You are a Research Supervisor managing a two-stage research process. "
    "You coordinate between {members} to conduct thorough market intelligence research.\n\n"
    "WORKFLOW:\n"
    "1. START: Always begin with 'Scout' to discover relevant URLs and understand the research landscape.\n"
    "2. SCOUT → ANALYST: After Scout finds URLs, use 'Analyst' when:\n"
    "   - The query requires specific details (pricing, features, specifications, comparisons)\n"
    "   - Scout has identified relevant URLs but you need the full content from those pages\n"
    "   - The user asks for detailed extraction or structured data\n"
    "   - Scout's summaries aren't sufficient to answer the query completely\n"
    "3. ANALYST → SCOUT: If Analyst extracts content but you need more sources, route back to Scout.\n"
    "4. FINISH: Only when you have enough information to provide a comprehensive answer.\n\n"
    "DECISION CRITERIA:\n"
    "- Use 'Scout' when: starting research, need to find more sources, or exploring new domains\n"
    "- Use 'Analyst' when: Scout has found URLs and you need detailed content extraction (pricing pages, feature lists, documentation, etc.)\n"
    "- Use 'FINISH' when: you have gathered sufficient information from both Scout and Analyst to answer the query comprehensively\n\n"
    "IMPORTANT: Don't finish too early. If Scout found URLs but you haven't extracted their detailed content yet, route to Analyst first."
)

class RouterOutput(TypedDict):
    next: Literal["Scout", "Analyst", "FINISH"]

def supervisor_node(state: AgentState):
    prompt = ChatPromptTemplate.from_messages([
        ("system", supervisor_prompt),
        MessagesPlaceholder(variable_name="messages"),
        ("system", f"Given the conversation, who should act next? Select one of: {options}")
    ]).partial(members=", ".join(members))
    
    chain = prompt | llm_smart.with_structured_output(RouterOutput)
    result = chain.invoke(state)
    next_agent = result["next"]
    
    # Format routing message with "Agent" suffix for clarity
    if next_agent == "FINISH":
        routing_text = "Routing to FINISH"
    else:
        routing_text = f"Routing to {next_agent} Agent"
    
    # Create a message for the supervisor decision so it appears in the stream
    decision_message = AIMessage(content=routing_text)
    
    # Log supervisor decision
    db_handler.log_step(state.get("session_id"), "Supervisor", "Routing", f"Routing to: {next_agent}")
    
    return {"next": next_agent, "messages": [decision_message]}
workflow = StateGraph(AgentState)
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("Scout", scout_node)
workflow.add_node("Analyst", analyst_node)

workflow.add_edge(START, "Supervisor")
workflow.add_edge("Scout", "Supervisor")
workflow.add_edge("Analyst", "Supervisor")

workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "Scout": "Scout",
        "Analyst": "Analyst",
        "FINISH": END
    }
)

market_graph = workflow.compile()