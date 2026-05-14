"""Standalone web scraper using Playwright for extracting content from web pages."""

import asyncio
import base64
import logging
import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
except ImportError:
    raise ImportError(
        "playwright is required for web scraping. "
        "Install it with: pip install playwright && playwright install"
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("web_scraper")


class WebScraper:
    """
    Standalone web scraper using Playwright for extracting content from web pages.
    
    Can be configured with:
        - start_urls: List of URLs to scrape
        - selectors: Dictionary of field names to CSS selectors
        - render_js: Whether to wait for JavaScript rendering
        - follow_links: Whether to follow links
        - max_depth: Maximum crawl depth
        - rate_limit: Requests per second
        - max_pages: Maximum pages to scrape
    """
    
    def __init__(
        self,
        start_urls: Optional[List[str]] = None,
        link_patterns: Optional[List[str]] = None,
        selectors: Optional[Dict[str, str]] = None,
        render_js: bool = True,
        follow_links: bool = True,
        max_depth: int = 1,
        rate_limit: float = 1.0,
        max_pages: int = 100,
        wait_for_selector: Optional[str] = None,
        include_html: bool = False,
        user_agent: Optional[str] = None,
        screenshot_enabled: bool = False,
        screenshot_full_page: bool = True,
        screenshot_selector: Optional[str] = None,
        screenshot_type: str = "png",
        screenshot_quality: Optional[int] = None,
        screenshot_save_to_file: bool = False,
        screenshot_output_dir: str = "./screenshots",
        debug_mode: bool = False,
    ):
        # URL configuration
        self.start_urls = start_urls or []
        self.link_patterns = link_patterns or []
        
        self.selectors = selectors or {"title": "title", "body": "body"}
        self.render_js = render_js
        self.follow_links = follow_links
        self.max_depth = max_depth
        self.rate_limit = rate_limit
        self.max_pages = max_pages
        self.wait_for_selector = wait_for_selector
        self.include_html = include_html
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.screenshot_enabled = screenshot_enabled
        self.screenshot_full_page = screenshot_full_page
        self.screenshot_selector = screenshot_selector
        self.screenshot_type = screenshot_type
        self.screenshot_quality = screenshot_quality
        self.screenshot_save_to_file = screenshot_save_to_file
        self.screenshot_output_dir = screenshot_output_dir
        self.debug_mode = debug_mode
        
        # Create screenshot directory if saving to file
        if self.screenshot_save_to_file and self.screenshot_enabled:
            Path(self.screenshot_output_dir).mkdir(parents=True, exist_ok=True)
        
        # Compile regex patterns for link filtering
        self.link_regex_patterns = []
        for pattern in self.link_patterns:
            if pattern and "*" in pattern:
                # Convert glob-like pattern to regex
                regex_pattern = re.escape(pattern).replace("\\*", ".*")
                self.link_regex_patterns.append(re.compile(f"^{regex_pattern}$"))
        
        if self.debug_mode:
            logger.debug(f"Compiled {len(self.link_regex_patterns)} link filter patterns")

    async def run(self) -> List[Dict[str, Any]]:
        """
        Run the scraper and return results.
        """
        if not self.start_urls:
            logger.error("No start URLs configured")
            return []

        logger.info(f"Starting scrape with {len(self.start_urls)} URLs. Max depth: {self.max_depth}, Max pages: {self.max_pages}")
        
        results: List[Dict[str, Any]] = []
        visited_urls = set()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=self.user_agent)
            
            try:
                # Queue for crawling: (url, depth)
                queue = [(url, 0) for url in self.start_urls]
                
                while queue and len(results) < self.max_pages:
                    url, depth = queue.pop(0)
                    
                    if url in visited_urls:
                        continue
                    
                    visited_urls.add(url)
                    
                    # Check if URL matches link patterns (if patterns are set and URL is not a start URL)
                    if self.link_regex_patterns and url not in self.start_urls:
                        matches_pattern = any(pattern.match(url) for pattern in self.link_regex_patterns)
                        if not matches_pattern:
                            logger.debug(f"Skipping {url} (does not match any link pattern)")
                            continue

                    # Rate limiting
                    if self.rate_limit > 0 and len(visited_urls) > 1:
                        await asyncio.sleep(1.0 / self.rate_limit)
                    
                    try:
                        page_content = await self._scrape_page(context, url, len(results))
                        
                        if page_content:
                            # Build output data structure
                            output_data = {
                                "url": url,
                                "title": page_content.get("title"),
                                "links": page_content.get("links"),
                                "extracted_fields": page_content.get("data"),
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                            
                            if self.include_html:
                                output_data["html"] = page_content.get("html")
                            
                            if self.screenshot_enabled:
                                if page_content.get("screenshot_base64"):
                                    output_data["screenshot_base64"] = page_content.get("screenshot_base64")
                                if page_content.get("screenshot_path"):
                                    output_data["screenshot_path"] = page_content.get("screenshot_path")
                            
                            results.append(output_data)
                            
                            # Follow links
                            if self.follow_links and depth < self.max_depth:
                                links = page_content.get("links", [])
                                for link in links:
                                    if link not in visited_urls:
                                        queue.append((link, depth + 1))
                                        
                    except Exception as e:
                        logger.error(f"Error scraping {url}: {str(e)}")
            
            finally:
                await context.close()
                await browser.close()
        
        logger.info(f"Completed scraping. Total pages: {len(results)}")
        return results

    async def _scrape_page(self, context: BrowserContext, url: str, index: int) -> Optional[Dict[str, Any]]:
        """Scrape a single page."""
        page = await context.new_page()
        try:
            logger.info(f"Scraping: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            
            if self.wait_for_selector:
                try:
                    await page.wait_for_selector(self.wait_for_selector, timeout=10000)
                except Exception:
                    logger.warning(f"Timeout waiting for selector {self.wait_for_selector} on {url}")

            # Extract data based on selectors
            extracted_data = {}
            if self.selectors and isinstance(self.selectors, dict):
                for field, selector in self.selectors.items():
                    try:
                        # Simple heuristic: if selector ends with @attr, get attribute
                        attr = None
                        clean_selector = selector
                        if "@" in selector:
                            parts = selector.rsplit("@", 1)
                            if len(parts) == 2:
                                clean_selector = parts[0].strip()
                                attr = parts[1].strip()
                        
                        if clean_selector:
                            element = page.locator(clean_selector).first
                            if await element.count() > 0:
                                if attr:
                                    value = await element.get_attribute(attr)
                                else:
                                    value = await element.text_content()
                                extracted_data[field] = value.strip() if value else None
                            
                    except Exception as e:
                        logger.warning(f"Failed to extract field '{field}' with selector '{selector}': {e}")
                        extracted_data[field] = None

            # Extract title
            title = await page.title()
            
            # Extract HTML if needed
            html = await page.content() if self.include_html else None

            screenshot_base64 = None
            screenshot_path = None
            if self.screenshot_enabled:
                screenshot_result = await self._capture_screenshot(page, url, index)
                if screenshot_result:
                    screenshot_base64 = screenshot_result.get("base64", None)
                    screenshot_path = screenshot_result.get("path", None)
            
            # Extract links for crawling
            links = []
            if self.follow_links:
                hrefs = await page.eval_on_selector_all("a[href]", "elements => elements.map(e => e.href)")
                # loop through hrefs and handle relative links
                for href in hrefs:
                    if href.startswith("http"):
                        links.append(href)
                    elif href.startswith("/"):
                        # Handle relative links
                        base_url = re.match(r"(https?://[^/]+)", url)
                        if base_url:
                            full_url = base_url.group(1) + href
                            links.append(full_url)

            return {
                "title": title,
                "data": extracted_data,
                "html": html,
                "links": links,
                "screenshot_base64": screenshot_base64,
                "screenshot_path": screenshot_path,
            }
            
        except Exception as e:
            logger.error(f"Failed to process page {url}: {e}")
            raise e
        finally:
            await page.close()

    async def _capture_screenshot(self, page: Page, url: str, index: int) -> Optional[Dict[str, str]]:
        """Capture a screenshot and return it as base64 string and/or save to file."""
        try:
            shot_bytes = None
            
            if self.screenshot_selector:
                locator = page.locator(self.screenshot_selector).first
                if await locator.count() == 0:
                    logger.warning(f"Screenshot selector not found: {self.screenshot_selector}")
                    return None
                shot_bytes = await locator.screenshot(
                    type=self.screenshot_type,
                    quality=self.screenshot_quality if self.screenshot_type == "jpeg" else None,
                )
            else:
                shot_bytes = await page.screenshot(
                    full_page=self.screenshot_full_page,
                    type=self.screenshot_type,
                    quality=self.screenshot_quality if self.screenshot_type == "jpeg" else None,
                )
            
            if not shot_bytes:
                return None
            
            result = {}
            
            # Always generate base64 if not saving to file, or if explicitly requested
            if not self.screenshot_save_to_file:
                result["base64"] = base64.b64encode(shot_bytes).decode("utf-8")
            
            # Save to file if requested
            if self.screenshot_save_to_file:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                ext = self.screenshot_type
                
                filename = f"{timestamp}_{index}.{ext}"
                filepath = os.path.join(self.screenshot_output_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(shot_bytes)
                
                result["path"] = filepath
                logger.debug(f"Screenshot saved to {filepath}")
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to capture screenshot: {e}")
            return None


async def main():
    """Main entry point for the scraper."""
    # Configuration for scraping https://www.ocif.pr.gov/
    scraper = WebScraper(
        start_urls=[
            "https://www.ocif.pr.gov/",
            "https://www.ocif.pr.gov/en",
        ],
        selectors={
            "title": "title",
            "h1": "h1",
            "description": "meta[name='description']@content",
        },
        render_js=True,
        follow_links=True, # modified
        max_depth=5, # modified
        rate_limit=1.0,
        max_pages=1000, # modified
        include_html=False,
        screenshot_enabled=False,
        debug_mode=True,
    )
    
    # Run the scraper
    results = await scraper.run()
    
    # Save results to JSON file
    output_file = "scrape_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to {output_file}")
    print(f"\nScraped {len(results)} pages.")
    print(f"Results saved to: {output_file}")
    
    # Print first result as sample
    if results:
        print("\nSample result:")
        print(json.dumps(results[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
