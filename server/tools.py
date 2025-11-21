import logging
import os

from langchain_core.tools import tool
from tavily import TavilyClient

tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
logger = logging.getLogger("market_intel.tools")

@tool
def tavily_search_research(query: str) -> str:
    """Search Tavily for competitive intel"""
    try:
        logger.info("[Tool] Searching for %s", query)
        response = tavily_client.search(
            query=query,
            search_depth="advanced",
            max_results=10,
            include_images=False,
            include_answer=True,
        )
        answer = response.get("answer", "No direct answer provided.")
        results = response.get("results", [])
        bullets = "\n".join(
            f"- {item.get('title', 'Untitled')}: {item.get('url')}"
            for item in results[:10]
        )
        return f"Search answer:\n{answer}\n\nTop sources:\n{bullets}"
    except Exception as e:
        return f"Error searching web: {str(e)}"

@tool
def tavily_map_site(url: str) -> str:
    """Map a site's structure using Tavily"""
    try:
        logger.info("[Tool] Mapping %s", url)
        response = tavily_client.map(
            url=url,
            max_depth=2,
            max_breadth=25,
            limit=25,
            instructions="Surface pricing, product, feature, and plans related paths.",
            include_images=False,
        )
        nodes = response.get("nodes", [])
        if not nodes:
            return f"No map results returned for {url}."
        lines = []
        for node in nodes[:25]:
            path = node.get("url", "")
            title = node.get("title") or node.get("description") or ""
            lines.append(f"- {path} :: {title}")
        return f"Discovered structure for {url}:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error mapping site: {str(e)}"

@tool
def tavily_crawl_summary(url: str) -> str:
    """Crawl a URL to get summary and context"""
    try:
        logger.info("[Tool] Crawling %s", url)
        response = tavily_client.crawl(
            url=url,
            extract_depth="advanced",
            format="markdown",
            limit=5,
            include_images=False,
        )
        pages = response.get("results", [])
        if not pages:
            return f"No crawl summary returned for {url}."
        summaries = []
        for page in pages[:5]:
            summaries.append(
                f"--- {page.get('url', url)} ---\n{page.get('content', '')[:1500]}..."
            )
        return "\n\n".join(summaries)
    except Exception as e:
        return f"Error crawling site: {str(e)}"

@tool
def tavily_extract_content(urls: str) -> str:
    """Extract raw text from URLs (comma-separated)"""
    try:
        url_list = [u.strip() for u in urls.split(",")]
        logger.info("[Tool] Extracting from %d URLs", len(url_list))
        response = tavily_client.extract(urls=url_list)

        extracted_data = []
        for result in response.get('results', []):
            extracted_data.append(f"--- Content from {result['url']} ---\n{result['raw_content'][:1500]}...")
            
        return "\n\n".join(extracted_data)
    except Exception as e:
        return f"Error extracting content: {str(e)}"