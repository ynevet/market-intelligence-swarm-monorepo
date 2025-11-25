import operator
from typing import Annotated, List, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END, START

from tools import (
    tavily_search_research,
    tavily_map_site,
    tavily_crawl_summary,
    tavily_extract_content,
)
from database import db_handler

llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_smart = ChatOpenAI(model="gpt-4o", temperature=0)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str
    session_id: str

scout_agent = create_agent(
    llm_fast,
    tools=[tavily_search_research, tavily_map_site],
    system_prompt="You are a Recon Scout. Use Tavily search and map tools to find relevant URLs and chart the research surface area. Identify specific URLs that the Analyst should investigate."
)

analyst_agent = create_agent(
    llm_fast,
    tools=[tavily_crawl_summary, tavily_extract_content],
    system_prompt="You are a Data Analyst. Use crawl and extract tools to gather detailed content from URLs identified by the Scout. Extract comprehensive information to answer the research questions."
)
def scout_node(state: AgentState):
    result = scout_agent.invoke(state)
    messages = result.get("messages") or []
    if not messages:
        fallback = AIMessage(content="Scout completed without returning a message.")
        db_handler.log_step(state.get("session_id"), "Scout", "Research", fallback.content)
        return {"messages": [fallback]}
    output = messages[-1]
    db_handler.log_step(state.get("session_id"), "Scout", "Research", output.content)
    return {"messages": [output]}

def analyst_node(state: AgentState):
    result = analyst_agent.invoke(state)
    messages = result.get("messages") or []
    if not messages:
        fallback = AIMessage(content="Analyst completed without returning extracted content.")
        db_handler.log_step(state.get("session_id"), "Analyst", "Extraction", fallback.content)
        return {"messages": [fallback]}
    output = messages[-1]
    db_handler.log_step(state.get("session_id"), "Analyst", "Extraction", output.content)
    return {"messages": [output]}

members = ["Scout", "Analyst"]
options = ["FINISH"] + members

supervisor_prompt = (
    "You are a Research Supervisor. Manage the following workers: {members}. "
    "Follow this workflow: "
    "1. Use 'Scout' to search and find relevant URLs. "
    "2. Once Scout identifies URLs, use 'Analyst' to extract detailed content from those URLs. "
    "3. You may alternate between Scout (for more URLs) and Analyst (for extraction) as needed. "
    "4. Return 'FINISH' only after Analyst has extracted sufficient details to answer the query comprehensively. "
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
    
    if next_agent == "FINISH":
        final_report_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Research Report Writer. Synthesize a comprehensive, well-structured market intelligence report from the conversation history. Format it in clear markdown with sections, headers, and bullet points. Include all key findings, data points, and insights discovered during the research."),
            MessagesPlaceholder(variable_name="messages"),
            ("system", "Generate the final comprehensive report based on all the research conducted.")
        ])
        final_chain = final_report_prompt | llm_smart
        final_message = final_chain.invoke(state)
        
        db_handler.log_step(state.get("session_id"), "Supervisor", "Routing", f"Routing to: {next_agent}")
        db_handler.log_step(state.get("session_id"), "Supervisor", "Final Report", final_message.content[:500] + "..." if len(final_message.content) > 500 else final_message.content)
        
        return {"next": next_agent, "messages": [final_message]}
    else:
        decision_message = AIMessage(content=f"Routing to {next_agent}")
        
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