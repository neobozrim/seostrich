from __future__ import annotations

import httpx
from bs4 import BeautifulSoup


def scrape_site(url: str, max_pages: int = 10) -> dict:
    """Scrape site structure and content for analysis."""
    # Normalize URL
    if not url.startswith("http"):
        url = f"https://{url}"
    
    pages = []
    visited = set()
    to_visit = [url]
    
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
            
            try:
                resp = client.get(current_url)
                if resp.status_code != 200:
                    continue
                
                visited.add(current_url)
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Extract page info
                title = soup.title.string if soup.title else ""
                h1 = soup.h1.get_text(strip=True) if soup.h1 else ""
                
                # Extract meta description
                meta_desc = ""
                meta_tag = soup.find("meta", attrs={"name": "description"})
                if meta_tag and meta_tag.get("content"):
                    meta_desc = meta_tag["content"]
                
                # Count words
                text = soup.get_text(strip=True)
                word_count = len(text.split())
                
                # Extract internal links
                internal_links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("/") or href.startswith(url):
                        full_url = href if href.startswith("http") else f"{url.rstrip('/')}/{href.lstrip('/')}"
                        if full_url.startswith(url) and full_url not in visited:
                            to_visit.append(full_url)
                            internal_links.append(href)
                
                pages.append({
                    "url": current_url,
                    "title": title,
                    "h1": h1,
                    "meta_description": meta_desc,
                    "word_count": word_count,
                    "internal_link_count": len(internal_links),
                })
                
            except Exception as e:
                continue
    
    return {
        "domain": url,
        "pages_scraped": len(pages),
        "pages": pages,
    }
