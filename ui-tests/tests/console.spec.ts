import { expect, test } from "@playwright/test";

const password = "Correct-Horse-9";
const email = `ui-${Date.now()}@example.com`;

test("login page is served and rejects bad credentials", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "NOVACLOUD" })).toBeVisible();
  await page.getByLabel("email").fill("nobody@example.com");
  await page.getByLabel("password").fill("wrong-password-1A");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
});

test("register, create an instance, see it running, stop and delete it", async ({ page }) => {
  await page.goto("/");
  await page.getByText("New here? Create an organization").click();
  await page.getByLabel("organization").fill("UI Tests");
  await page.getByLabel("email").fill(email);
  await page.getByLabel("password").fill(password);
  await page.getByRole("button", { name: "Create organization" }).click();

  await expect(page.getByText("Role:")).toBeVisible();
  await expect(page.getByText("owner", { exact: true })).toBeVisible();

  await page.getByRole("navigation").getByRole("button", { name: "Instances" }).click();
  await page.getByLabel("name").fill("ui-web");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  const row = page.getByRole("row", { name: /ui-web/ });
  await expect
    .poll(async () => {
      await page.getByRole("button", { name: "Refresh" }).first().click();
      return row.innerText();
    }, { timeout: 90_000, intervals: [2_000] })
    .toContain("running");

  await row.getByRole("button", { name: "Stop" }).click();
  await expect
    .poll(async () => {
      await page.getByRole("button", { name: "Refresh" }).first().click();
      return row.innerText();
    }, { timeout: 90_000, intervals: [2_000] })
    .toContain("stopped");

  page.once("dialog", d => d.accept("ui-web"));
  await row.getByRole("button", { name: "Delete" }).click();
  await expect
    .poll(async () => {
      await page.getByRole("button", { name: "Refresh" }).first().click();
      return page.getByRole("row", { name: /ui-web/ }).count();
    }, { timeout: 90_000, intervals: [2_000] })
    .toBe(0);
});

test("audit log is visible and sign out returns to login", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("email").fill(email);
  await page.getByLabel("password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Audit" }).click();
  await expect(page.getByRole("cell", { name: "instance.create" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
