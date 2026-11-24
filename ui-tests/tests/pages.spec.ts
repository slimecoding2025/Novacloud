import { expect, test, type Page } from "@playwright/test";

const password = "Correct-Horse-9";

async function register(page: Page) {
  const email = `pages-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/");
  await page.getByText("New here? Create an organization").click();
  await page.getByLabel("organization").fill("UI Pages");
  await page.getByLabel("email").fill(email);
  await page.getByLabel("password").fill(password);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByText("Role:")).toBeVisible();
}

const tab = (page: Page, name: string) => page.getByRole("navigation").getByRole("button", { name }).click();

test("objects: upload, list with checksum, delete", async ({ page }) => {
  await register(page);
  await tab(page, "Objects");
  await page.getByLabel("upload").setInputFiles({ name: "hello.txt", mimeType: "text/plain", buffer: Buffer.from("hello novacloud") });
  const row = page.getByRole("row", { name: /hello\.txt/ });
  await expect(row).toContainText("15 B");
  await expect(row.getByRole("link", { name: "Download" })).toBeVisible();
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("row", { name: /hello\.txt/ })).toHaveCount(0);
});

test("members: add a viewer and see the role", async ({ page }) => {
  await register(page);
  await tab(page, "Members");
  await page.getByLabel("email").fill(`viewer-${Date.now()}@example.com`);
  await page.getByLabel("password").fill("Another-Pass-42");
  await page.getByLabel("role").selectOption("viewer");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("row", { name: /viewer-.*viewer/ })).toBeVisible();
});

test("networks: create a real network and subnet, then remove them", async ({ page }) => {
  await register(page);
  await tab(page, "Networks");
  await page.getByLabel("network name").fill("ui-net");
  await page.getByLabel("cidr", { exact: true }).fill("10.88.0.0/16");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: /ui-net/ })).toBeVisible();

  await page.getByLabel("parent network").selectOption({ label: "ui-net" });
  await page.getByLabel("subnet name").fill("ui-sub");
  await page.getByLabel("subnet cidr").fill("10.88.1.0/24");
  await page.getByRole("button", { name: "Add subnet" }).click();
  const sub = page.getByRole("listitem").filter({ hasText: "ui-sub" });
  await expect(sub).toContainText("10.88.1.0/24");
  await expect(sub).toContainText("0 allocated");

  await sub.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "ui-sub" })).toHaveCount(0);
  await page.getByRole("heading", { name: /ui-net/ }).getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("heading", { name: /ui-net/ })).toHaveCount(0);
});
