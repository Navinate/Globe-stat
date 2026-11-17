import sys, time
from playwright.sync_api import sync_playwright

path = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome",
                          args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 420, "height": 900}, device_scale_factor=2)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + path)
    time.sleep(2)
    for r in range(3):
        print("PROMPT", pg.locator(".prompt").inner_text())
        bb = pg.locator("canvas").bounding_box()
        for dx, dy in [(x / 10, y / 10) for y in range(-3, 4) for x in range(-3, 4)]:
            pg.mouse.move(bb["x"] + bb["width"] * (0.5 + dx), bb["y"] + bb["height"] * (0.5 + dy))
            pg.mouse.down(); pg.mouse.up(); time.sleep(0.4)
            if pg.locator("button:has-text('Lock in')").is_enabled():
                break
        pg.screenshot(path=f"shots/{r}a.png")
        pg.click("button:has-text('Lock in')")
        time.sleep(1.5)
        pg.screenshot(path=f"shots/{r}b.png")
        print("  ", pg.locator(".card").inner_text().replace("\n", " | "))
        pg.locator(".card button").click()
        time.sleep(0.8)
    pg.screenshot(path="shots/end.png", full_page=True)
    pg.reload(); time.sleep(1.5)
    print("AFTER RELOAD:", pg.locator(".card").inner_text().replace("\n", " | "))
    print("errors:", errs)
    b.close()
