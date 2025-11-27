import logging
import os

from langchain_core.tools import tool
from tavily import TavilyClient

tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
logger = logging.getLogger("market_intel.tools")

@tool
def tavily_search_research(query: str, topic: str = "general") -> str:
    """Search Tavily for competitive intel.
    
    Args:
        query: Search query (max 400 chars)
        topic: 'general' for broad search or 'news' for current events
    """
    try:
        # Tavily API has 400 char limit
        if len(query) > 400:
            query = query[:400]
        
        logger.info("[Tool] Searching for %s (topic=%s)", query, topic)
        response = tavily_client.search(
            query=query,
            search_depth="advanced",
            topic=topic if topic in ("general", "news") else "general",
            max_results=10,
            include_images=False,
            include_answer=True,
        )
        answer = response.get("answer", "No direct answer provided.")
        results = response.get("results", [])
        
        # Include scores to help filter relevant results (best practice)
        bullets = "\n".join(
            f"- [{item.get('score', 0):.2f}] {item.get('title', 'Untitled')}: {item.get('url')}"
            for item in results[:10]
        )
        return f"Search answer:\n{answer}\n\nTop sources (with relevance scores):\n{bullets}"
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
            max_depth=2,
            max_breadth=10,
            limit=5,
            extract_depth="advanced",
            format="markdown",
            include_images=False,
        )
        pages = response.get("results", [])
        if not pages:
            return f"No crawl summary returned for {url}."
        summaries = []
        for page in pages[:5]:
            content = page.get("raw_content") or page.get("content") or ""
            summaries.append(
                f"--- {page.get('url', url)} ---\n{content[:1500]}..."
            )
        return "\n\n".join(summaries)
    except Exception as e:
        return f"Error crawling site: {str(e)}"

@tool
def tavily_extract_content(urls: str, use_advanced: bool = False) -> str:
    """Extract raw text from URLs (comma-separated).
    
    Args:
        urls: Comma-separated list of URLs to extract content from
        use_advanced: Use advanced extraction for complex pages (LinkedIn, dynamic content)
    """
    try:
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        if not url_list:
            return "No valid URLs provided."
        
        logger.info("[Tool] Extracting from %d URLs (advanced=%s)", len(url_list), use_advanced)
        response = tavily_client.extract(
            urls=url_list,
            extract_depth="advanced" if use_advanced else "basic"
        )

        extracted_data = []
        for result in response.get('results', []):
            url = result.get('url', 'Unknown URL')
            content = result.get('raw_content') or result.get('content') or "No content extracted"
            extracted_data.append(f"--- Content from {url} ---\n{content[:1500]}...")
        
        # Report any failed extractions
        failed = response.get('failed_results', [])
        if failed:
            extracted_data.append(f"\n[Warning: Failed to extract from {len(failed)} URL(s)]")
            
        return "\n\n".join(extracted_data) if extracted_data else "No content could be extracted."
    except Exception as e:
        return f"Error extracting content: {str(e)}"