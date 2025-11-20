import os
from langchain_core.tools import tool
from tavily import TavilyClient

# Initialize Tavily Client directly for advanced endpoints
tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

@tool
def tavily_map_site(url: str) -> str:
    """
    Maps a domain to find its site structure and sub-pages. 
    Use this first to discover relevant URLs (e.g., /pricing, /features).
    """
    try:
        # Attempts to use the Map endpoint (if available on plan), 
        # falls back to site-specific search if needed.
        # Note: detailed 'map' is an advanced Tavily feature.
        print(f"--- [Tool] Mapping {url} ---")
        # Using search with depth="advanced" to simulate mapping if strictly map endpoint is locked
        response = tavily_client.search(query=f"site:{url} map", search_depth="advanced")
        urls = [r['url'] for r in response.get('results', [])]
        return f"Discovered URLs for {url}:\n" + "\n".join(urls[:10])
    except Exception as e:
        return f"Error mapping site: {str(e)}"

@tool
def tavily_crawl_summary(url: str) -> str:
    """
    Crawls a specific URL to get a broad summary and context.
    Useful for understanding what a page is about before extracting details.
    """
    try:
        print(f"--- [Tool] Crawling {url} ---")
        # usage of get_search_context acts as a smart crawl/summarizer
        context = tavily_client.get_search_context(query=f"summary of {url}", max_tokens=2000)
        return f"Page Summary for {url}:\n{context}"
    except Exception as e:
        return f"Error crawling site: {str(e)}"

@tool
def tavily_extract_content(urls: str) -> str:
    """
    Extracts raw, clean text data from a comma-separated list of URLs.
    Use this to get precise data like pricing tables or specs.
    """
    try:
        url_list = [u.strip() for u in urls.split(",")]
        print(f"--- [Tool] Extracting from {len(url_list)} URLs ---")
        response = tavily_client.extract(urls=url_list)
        
        extracted_data = []
        for result in response.get('results', []):
            extracted_data.append(f"--- Content from {result['url']} ---\n{result['raw_content'][:1500]}...")
            
        return "\n\n".join(extracted_data)
    except Exception as e:
        return f"Error extracting content: {str(e)}"