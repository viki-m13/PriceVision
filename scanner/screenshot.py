"""Screenshot capture using Playwright.

Takes desktop and mobile screenshots of pages for audit reports.
"""

from __future__ import annotations

import os
from pathlib import Path


async def capture_screenshots(
    url: str,
    output_dir: str = "screenshots",
    desktop: bool = True,
    mobile: bool = True,
    full_page: bool = True,
) -> dict[str, str]:
    """Capture desktop and mobile screenshots of a URL.

    Returns dict mapping viewport name to file path.
    """
    # Import here so playwright is only required when screenshots are needed
    from playwright.async_api import async_playwright

    os.makedirs(output_dir, exist_ok=True)

    # Sanitize URL for filename
    safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
    if len(safe_name) > 80:
        safe_name = safe_name[:80]

    paths: dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        if desktop:
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                path = str(Path(output_dir) / f"{safe_name}_desktop.png")
                await page.screenshot(path=path, full_page=full_page)
                paths["desktop"] = path
            except Exception:
                pass
            await context.close()

        if mobile:
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/16.0 Mobile/15E148 Safari/604.1"
                ),
                is_mobile=True,
                has_touch=True,
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                path = str(Path(output_dir) / f"{safe_name}_mobile.png")
                await page.screenshot(path=path, full_page=full_page)
                paths["mobile"] = path
            except Exception:
                pass
            await context.close()

        await browser.close()

    return paths


async def capture_form_interaction(
    url: str,
    output_dir: str = "screenshots",
) -> str | None:
    """Try to find and interact with the main form, screenshot the result.

    Returns path to screenshot or None.
    """
    from playwright.async_api import async_playwright

    os.makedirs(output_dir, exist_ok=True)
    safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
    if len(safe_name) > 80:
        safe_name = safe_name[:80]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)

            # Find the first visible form
            form = await page.query_selector("form")
            if not form:
                await browser.close()
                return None

            # Try clicking the submit button without filling anything
            # This tests if the form shows proper validation
            submit = await form.query_selector(
                'button[type="submit"], input[type="submit"], button:not([type])'
            )
            if submit:
                await submit.click()
                await page.wait_for_timeout(1500)

            path = str(Path(output_dir) / f"{safe_name}_form_test.png")
            await page.screenshot(path=path, full_page=False)
            await browser.close()
            return path

        except Exception:
            await browser.close()
            return None
