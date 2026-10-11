// The slider at the top left seats a council of 2 to 6 (Lucas, 2026-10-11).
// Runs against the built app, like gate.spec.ts.
import { expect, type Page, test } from "@playwright/test";

const SLIDER = { name: "Seats at the table" } as const;

async function open(page: Page, route: string, size = { width: 1440, height: 830 }) {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize(size);
  await page.goto(`/#${route}`);
  await page.waitForLoadState("networkidle");
  return errors;
}

/** The address must stay as it is for a moment (a key that should do nothing). */
async function staysAt(page: Page, url: string) {
  for (let i = 0; i < 4; i++) {
    await page.waitForTimeout(80);
    expect(page.url()).toBe(url);
  }
}

test("the slider sits at the left end of the top bar and seats two to six by keyboard", async ({ page }) => {
  const errors = await open(page, "/sample/lease?scene=debating");
  const seats = page.locator("[data-part=seat]");
  const thumb = page.getByRole("slider", SLIDER);
  const title = page.getByRole("button", { name: /^Council of \d$/ });
  await expect(seats).toHaveCount(5);
  await expect(thumb).toHaveAttribute("aria-valuemin", "2");
  await expect(thumb).toHaveAttribute("aria-valuemax", "6");
  await expect(thumb).toHaveAttribute("aria-valuenow", "5");

  const box = await page.locator("[data-part=council-slider]").boundingBox();
  if (!box) throw new Error("no slider");
  expect(box.x + box.width, "in the left third of the window").toBeLessThan(1440 / 3);
  expect(box.y + box.height, "in the top bar").toBeLessThanOrEqual(48);

  await thumb.focus();
  await page.keyboard.press("Home");
  for (const n of [2, 3, 4, 5, 6]) {
    await expect(seats).toHaveCount(n);
    await expect(title).toHaveText(`Council of ${n}`);
    await expect(thumb).toHaveAttribute("aria-valuenow", String(n));
    await expect(thumb).toHaveAttribute("aria-valuetext", `${n} seats`);
    await expect(page.locator("[data-part=seat-name]")).toHaveCount(n);
    await expect(thumb).toBeFocused();
    if (n < 6) await page.keyboard.press("ArrowRight");
  }
  // both ends stop
  const atSix = page.url();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("End");
  await staysAt(page, atSix);
  await page.keyboard.press("Home");
  await expect(seats).toHaveCount(2);
  const atTwo = page.url();
  await page.keyboard.press("ArrowLeft");
  await staysAt(page, atTwo);
  // a digit or Space on the slider is not a shortcut: no side sheet opens, the slider keeps the keyboard
  await page.keyboard.press("1");
  await page.keyboard.press(" ");
  await expect(page.locator("[data-part=seat-sheet]")).toHaveCount(0);
  await expect(thumb).toBeFocused();
  expect(errors).toEqual([]);
});

test("dragging the slider seats each size on the way, and a reload keeps the council", async ({ page }) => {
  const errors = await open(page, "/sample/lease?scene=debating");
  const seats = page.locator("[data-part=seat]");
  const thumb = page.getByRole("slider", SLIDER);
  const track = page.locator("[data-part=council-slider] [data-orientation=horizontal]").first();
  const rail = await track.boundingBox();
  const knob = await thumb.boundingBox();
  if (!rail || !knob) throw new Error("no slider");
  const y = rail.y + rail.height / 2;
  // press on the thumb, drag to the far left in small steps, hold, then to the far right
  await page.mouse.move(knob.x + knob.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(rail.x + 1, y, { steps: 20 });
  await expect(seats).toHaveCount(2);
  await page.mouse.move(rail.x + rail.width - 1, y, { steps: 20 });
  await expect(seats).toHaveCount(6);
  await page.mouse.move(rail.x + rail.width / 2, y, { steps: 10 });
  await page.mouse.up();
  await expect(seats).toHaveCount(4);
  expect(page.url()).toContain("/sample/lease-4?scene=debating");
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(seats).toHaveCount(4);
  await expect(page.getByRole("slider", SLIDER)).toHaveAttribute("aria-valuenow", "4");
  expect(errors).toEqual([]);
});

test("from a vote, a pause or a waiting note the slider always lands on a table", async ({ page }) => {
  for (const scene of ["vote", "paused", "owner-note", "agreed", "researching"]) {
    const errors = await open(page, `/sample/lease?scene=${scene}`);
    const thumb = page.getByRole("slider", SLIDER);
    await thumb.focus();
    await page.keyboard.press("Home");
    for (const n of [2, 3, 4, 5, 6]) {
      await expect(page.getByRole("button", { name: `Council of ${n}` }), `${scene}, ${n} seats`).toBeVisible();
      await expect(page.locator("[data-part=seat]"), `${scene}, ${n} seats: a table, not the answer`).toHaveCount(n);
      await expect(page.locator("[data-part=answer]")).toHaveCount(0);
      if (n < 6) await page.keyboard.press("ArrowRight");
    }
    expect(errors, scene).toEqual([]);
  }
});

test("before a question is sent the slider changes the council and nothing else", async ({ page }) => {
  // the new chat: what is typed stays, the screen stays the new chat, no side sheet opens
  let errors = await open(page, "/sample/new");
  const box = page.getByRole("textbox").first();
  await box.fill("my own question");
  const thumb = page.getByRole("slider", SLIDER);
  await thumb.focus();
  for (const key of ["ArrowLeft", "ArrowLeft", "End", "Home"]) await page.keyboard.press(key);
  await expect(page.getByRole("button", { name: "Council of 2" })).toBeVisible();
  await expect(box).toHaveValue("my own question");
  await expect(page.locator("[data-part=seat-picker]")).toHaveCount(0);
  await expect(thumb).toBeFocused();
  expect(page.url()).toContain("/sample/new?");
  expect(page.url()).toContain("seats=2");
  await expect(page.getByText("2 seats, 5 min")).toBeVisible();
  expect(errors).toEqual([]);

  // the asking screen with its seat picker shut: it stays shut while sliding
  errors = await open(page, "/sample/lease?scene=asking&picker=0");
  const again = page.getByRole("slider", SLIDER);
  await again.focus();
  for (const n of [4, 3, 2]) {
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByRole("button", { name: `Council of ${n}` })).toBeVisible();
    await expect(page.locator("[data-part=seat-picker]")).toHaveCount(0);
    await expect(again).toBeFocused();
  }
  expect(errors).toEqual([]);
});

test("a seven-seat review scene stretches the slider to seven, and six is one step away", async ({ page }) => {
  const errors = await open(page, "/sample/lease-7?scene=vote");
  const thumb = page.getByRole("slider", SLIDER);
  await expect(thumb).toHaveAttribute("aria-valuemax", "7");
  await expect(thumb).toHaveAttribute("aria-valuenow", "7");
  await thumb.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("button", { name: "Council of 6" })).toBeVisible();
  await expect(page.locator("[data-part=seat]")).toHaveCount(6);
  await expect(page.getByRole("slider", SLIDER)).toHaveAttribute("aria-valuemax", "6");
  expect(errors).toEqual([]);
});

test("in the smallest window the slider is still whole and no name is cut in half", async ({ page }) => {
  const errors = await open(page, "/sample/lease-6?scene=debating", { width: 800, height: 568 });
  const slider = await page.locator("[data-part=council-slider]").boundingBox();
  const pill = await page.locator("[data-part=status-pill]").boundingBox();
  if (!slider || !pill) throw new Error("no slider or pill");
  expect(slider.x + slider.width).toBeLessThan(pill.x);
  // every seat name the bar shows is wholly inside the bar; the rest are out of sight, never half shown
  const list = page.getByRole("list", { name: "Seated" });
  const bar = await list.boundingBox();
  if (!bar) throw new Error("no seat list");
  let whole = 0;
  for (const item of await list.getByRole("listitem").all()) {
    const b = await item.boundingBox();
    if (!b) continue;
    const inside = b.y >= bar.y - 1 && b.y + b.height <= bar.y + bar.height + 1;
    const outside = b.y >= bar.y + bar.height - 1;
    expect(inside || outside, "a name is either wholly shown or wholly hidden").toBe(true);
    if (inside) whole++;
  }
  expect(whole).toBeGreaterThanOrEqual(3);
  expect(errors).toEqual([]);
});
