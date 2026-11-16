import { execSync } from "node:child_process";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

/** The full demo script: onboarding, day 1, day 5, conversation, invoice, approve, batch. */
const SHOTS = process.env.E2E_SHOTS;
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
};

test.beforeAll(() => {
  execSync("docker compose exec -T api python -m seeds.run", { cwd: path.resolve(__dirname, "../..") });
});

test("demo del cierre de octubre", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  // 1. Users onboard with a mandatory ARCA link.
  for (const name of ["Mateo", "Martina"]) {
    await page.goto("/app");
    await page.getByRole("link", { name: new RegExp(name) }).click();
    await shot(page, `01-${name}-home`);
    await page.getByRole("button", { name: "Conocer más" }).click();
    await shot(page, `02-${name}-oferta`);
    await page.getByRole("button", { name: "Quiero mi contador" }).click();
    await page.getByRole("checkbox").check();
    await shot(page, `03-${name}-adhesion`);
    await page.getByRole("button", { name: "Continuar" }).click();
    await page.getByRole("button", { name: "Vincular con ARCA" }).click();
    await expect(page.getByText("Listo: tu cuenta está vinculada")).toBeVisible();
    await shot(page, `04-${name}-vinculado`);
  }
  await expect(page.getByText(/Cobraste USD 1\.200 de/)).toBeVisible();
  await expect(page.getByText(/¿Quién es J\. Pérez\?/)).toBeVisible();
  const martinaUrl = page.url();

  // 2. Day 1: the close starts.
  const console_ = await context.newPage();
  console_.on("pageerror", (e) => errors.push(e.message));
  await console_.goto("/consola");
  await expect(console_.getByText(/todavía no arrancó/)).toBeVisible();
  await shot(console_, "05-bandeja-sin-arrancar");
  await console_.getByRole("button", { name: "Simular día 1: iniciar cierre" }).first().click();
  await expect(console_.getByRole("link", { name: "Martina Ríos" })).toBeVisible({ timeout: 20_000 });
  await expect(console_.locator("tr", { hasText: "Mateo" }).getByText("Listo")).toBeVisible({ timeout: 20_000 });
  await shot(console_, "06-bandeja-dia-1");

  // 3. Day 5: the unanswered question goes to the accountant.
  await console_.getByRole("button", { name: "Simular día 5: vence el plazo" }).click();
  await console_.waitForTimeout(4_000);
  await console_.getByRole("link", { name: "Martina Ríos" }).click();
  await expect(console_.getByText("Cobro sin facturar · USD 1.200")).toBeVisible();
  await shot(console_, "07-detalle-martina");

  // 4. Conversation inside the alert.
  await console_.getByRole("button", { name: "Escribirle a Martina" }).click();
  await console_.getByRole("button", { name: "Enviar" }).click();
  await expect(console_.getByText(/podés emitirla desde la app/).first()).toBeVisible();
  await shot(console_, "08-conversacion");

  // 5. Martina invoices from the app and replies.
  await page.goto(martinaUrl);
  await expect(page.getByText("Tu contador te escribió")).toBeVisible({ timeout: 10_000 });
  await shot(page, "09-martina-mensaje");
  await page.getByRole("button", { name: "Facturar este cobro" }).click();
  await shot(page, "10-martina-facturar");
  await page.getByRole("button", { name: "Emitir factura" }).click();
  await page.getByPlaceholder("Escribile a tu contador").fill("Me había olvidado. Ya la emití desde la app.");
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.getByText("Me había olvidado. Ya la emití desde la app.")).toBeVisible();
  await shot(page, "11-martina-respondio");

  // 6. The unbilled alert disappears; apply the suggestion; approve with A.
  await expect(console_.getByText("Cobro sin facturar · USD 1.200")).toBeHidden({ timeout: 20_000 });
  await console_.getByRole("button", { name: "Aplicar sugerencia" }).click();
  await expect(console_.getByText(/Deshacer/)).toBeVisible();
  await expect(console_.getByRole("checkbox")).toBeVisible({ timeout: 10_000 });
  await shot(console_, "12-listo-para-aprobar");
  await console_.getByRole("checkbox").check();
  await console_.keyboard.press("a");
  await expect(console_.getByText(/Aprobado: snapshot congelado/)).toBeVisible();
  await shot(console_, "13-aprobado");

  // 7. Batch with Mateo.
  await console_.goto("/consola/lote");
  await expect(console_.getByRole("heading", { name: /Aprobar 1 cierre/ })).toBeVisible();
  await shot(console_, "14-lote");
  await console_.getByRole("checkbox").nth(1).check();
  await console_.getByRole("button", { name: /Aprobar y notificar/ }).click();
  await expect(console_.getByText(/cierres? aprobados?/)).toBeVisible();
  await shot(console_, "15-lote-aprobado");

  // 8. Both users see their approved close.
  await console_.goto("/consola");
  await expect(console_.locator("tr", { hasText: "Mateo" }).getByText("Notificado")).toBeVisible({ timeout: 20_000 });
  await expect(console_.getByText(/completo/)).toBeVisible();
  await shot(console_, "16-bandeja-final");
  await page.goto(martinaUrl);
  await expect(page.getByText("Revisado por tu contador")).toBeVisible({ timeout: 20_000 });
  await shot(page, "17-martina-notificada");

  expect(errors, errors.join("\n")).toEqual([]);
});
