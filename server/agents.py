import os
import operator
from typing import Annotated, List, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import create_react_agent

from tools import tavily_map_site, tavily_crawl_summary, tavily_extract_content
from database import db_handler

# --- Config ---
# Use gpt-4o-mini for workers to save costs, gpt-4o for supervisor
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_smart = ChatOpenAI(model="gpt-4o", temperature=0)

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str
    session_id: str

# --- Worker Agents ---
# 1. The Scout: Maps site structure
scout_agent = create_react_agent(
    llm_fast, 
    [tavily_map_site, tavily_crawl_summary],
    prompt="You are a Recon Scout. Find relevant URLs for the user's target topic using map and crawl tools."
)

# 2. The Analyst: Extracts deep data
analyst_agent = create_react_agent(
    llm_fast,
    [tavily_extract_content],
    prompt="You are a Data Analyst. Extract raw content from specific URLs provided by the Scout to answer specific questions."
)

# --- Node Wrappers (with DB Logging) ---
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

# --- Supervisor (Router) ---
members = ["Scout", "Analyst"]
options = ["FINISH"] + members

supervisor_prompt = (
    "You are a Research Supervisor. Manage the following workers: {members}. "
    "1. Use 'Scout' to find URLs and site structure. "
    "2. Use 'Analyst' to extract specific details from those URLs. "
    "3. Return 'FINISH' when you have a comprehensive answer. "
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
    return {"next": result["next"]}

# --- Graph Construction ---
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