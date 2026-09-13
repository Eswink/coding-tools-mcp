"""Offline regression: readiness checks must not invoke user-decision callbacks.

This test uses a blank browser page and makes no HTTP requests. It proves the
Playwright predicate contract, not the application's native approval behavior.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        executable = Path(os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"))
        browser = playwright.chromium.launch(
            executable_path=str(executable) if executable.is_file() else None,
            headless=True,
        )
        try:
            page = browser.new_page()
            results = []
            for name in ("releaseConfirm", "releaseSave"):
                def reset() -> None:
                    page.evaluate("""(name) => {
                        window.resolverCalls = 0;
                        window.decision = 'pending';
                        window.pendingDecision = new Promise(resolve => {
                            window[name] = value => {
                                window.resolverCalls += 1;
                                resolve(value);
                            };
                        });
                        window.pendingDecision.then(value => {
                            window.decision = value === undefined ? 'undefined' : value;
                        });
                    }""", name)

                reset()
                try:
                    page.wait_for_function(f"window.{name}", timeout=250)
                except PlaywrightTimeoutError:
                    pass
                else:
                    raise AssertionError("the old function-valued predicate must time out")
                assert page.evaluate("window.resolverCalls") > 0
                assert page.evaluate("window.decision") is None  # Python arg=None arrives as JS null.
                results.append({"callback": name, "baseline": "side effect and timeout reproduced"})

                reset()
                page.wait_for_function(f"typeof window.{name} === 'function'", timeout=1000)
                assert page.evaluate("window.resolverCalls") == 0
                assert page.evaluate("window.decision") == "pending"
                page.evaluate("name => window[name](true)", name)
                page.wait_for_function("window.decision === true", timeout=1000)
                assert page.evaluate("window.resolverCalls") == 1
                results[-1]["candidate"] = "readiness is side-effect-free; explicit decision required"
            print(json.dumps({"status": "passed", "transport": "blank page; no network", "tests": results}, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
