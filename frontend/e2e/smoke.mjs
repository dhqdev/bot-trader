// Teste de ponta a ponta: navega por TODAS as telas clicando no menu, como uma
// pessoa faria (computador e celular), e falha se aparecer qualquer erro de
// JavaScript ou a tela de erro. Abrir cada tela com page.goto não basta: vários
// erros só aparecem ao TROCAR de tela, quando o React desmonta a anterior.
//
// Uso: backend rodando com o frontend compilado, depois `npm run test:e2e`.
//   E2E_BASE_URL (padrão http://127.0.0.1:8010), E2E_EMAIL, E2E_PASSWORD
//   E2E_CHROME_PATH: usa um Chrome já instalado em vez do Chromium do Playwright
import { chromium } from "playwright";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8010";
const EMAIL = process.env.E2E_EMAIL ?? "e2e@local.dev";
const PASSWORD = process.env.E2E_PASSWORD ?? "senha-e2e-123";
const launch = process.env.E2E_CHROME_PATH ? { executablePath: process.env.E2E_CHROME_PATH } : {};
const CRASH = /Unexpected Application Error|Esta tela encontrou um erro/;

const failures = [];
let steps = 0;

async function assertHealthy(page, errors, label) {
  steps += 1;
  await page.waitForTimeout(250);
  const body = await page.locator("body").innerText();
  if (CRASH.test(body)) failures.push(`${label}: tela de erro -> ${body.split("\n").slice(0, 3).join(" | ")}`);
  while (errors.length) failures.push(`${label}: erro de JavaScript -> ${errors.shift()}`);
}

async function login(page) {
  await page.goto(`${BASE}/`);
  await page.waitForSelector("form");
  const registering = await page.getByText("Crie sua conta").count();
  if (registering) await page.locator("input").first().fill("E2E");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForSelector('h1:has-text("Painel")', { timeout: 30000 });
}

async function ensureBot(page) {
  // cria um bot simulado pela API (precisa da OKX; sem acesso, os passos do bot são pulados)
  return page.evaluate(async () => {
    const list = await (await fetch("/api/bots", { credentials: "include" })).json();
    if (Array.isArray(list) && list.length) return list[0].name;
    const res = await fetch("/api/bots", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "E2E Squeeze", symbol: "BTCUSDT", interval: "4h", strategy: "squeeze", mode: "paper" }),
    });
    return res.ok ? (await res.json()).name : null;
  });
}

async function tour(browser, { label, viewport, navSelector, names }) {
  const context = await browser.newContext({ viewport, isMobile: viewport.width < 768, hasTouch: viewport.width < 768 });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  // a política de segurança (CSP) não pode bloquear nada do próprio app
  page.on("console", (msg) => {
    if (msg.type() === "error" && /Content Security Policy|Refused to (load|execute|apply)/i.test(msg.text())) errors.push(`CSP: ${msg.text()}`);
  });
  await login(page);
  const botName = await ensureBot(page);
  await assertHealthy(page, errors, `${label} painel`);

  const go = async (key, heading) => {
    await page.locator(navSelector).getByRole("link", { name: names[key], exact: true }).click();
    try {
      await page.waitForSelector(`h1:has-text("${heading}")`, { timeout: 15000 });
    } catch {
      await assertHealthy(page, errors, `${label} ${heading}`);
      throw new Error(`${label}: a tela "${heading}" não abriu (navegação interrompida)`);
    }
    await assertHealthy(page, errors, `${label} ${heading}`);
  };

  await go("bots", "Bots");
  if (botName) {
    await page.getByText(botName, { exact: true }).first().click();
    await page.waitForSelector(`h1:has-text("${botName}")`, { timeout: 15000 });
    await page.waitForTimeout(1500); // gráfico e condições carregam
    await assertHealthy(page, errors, `${label} detalhe do bot`);
    await go("bots", "Bots");
  } else {
    console.log(`  (${label}) sem acesso à OKX: passos do detalhe do bot pulados`);
  }

  await page.getByRole("button", { name: "Novo bot" }).click();
  await page.waitForSelector('h1:has-text("Novo bot")');
  for (const tier of ["Rápido · minutos", "Médio · horas", "Lento · dias"]) {
    await page.getByRole("button", { name: tier }).click();
    await page.getByRole("button", { name: "Usar", exact: true }).first().click();
    await assertHealthy(page, errors, `${label} novo bot / ${tier}`);
  }

  await go("lab", "Laboratório");
  await page.getByRole("button", { name: "Médio · horas" }).click();
  await page.getByRole("button", { name: "Usar", exact: true }).first().click();
  await page.getByRole("button", { name: "Como usar o laboratório" }).click();
  await assertHealthy(page, errors, `${label} laboratório / perfil`);

  await go("ai", "Análise com IA");
  for (const tab of ["Piloto automático", "Notícias e sentimento", "Conversa"]) {
    await page.locator('nav[aria-label="Seções da IA"]').getByRole("link", { name: tab, exact: true }).click();
    await page.waitForTimeout(800);
    await assertHealthy(page, errors, `${label} IA / ${tab}`);
  }
  await go("settings", "Configurações");
  await page.getByText("Segurança da conta").first().waitFor({ timeout: 15000 });
  await assertHealthy(page, errors, `${label} configurações / segurança`);
  await go("dashboard", "Painel");

  // troca rápida entre telas e voltar/avançar do navegador
  for (const [key, heading] of [["bots", "Bots"], ["lab", "Laboratório"], ["ai", "Análise com IA"], ["dashboard", "Painel"]]) await go(key, heading);
  await page.goBack();
  await page.goBack();
  await page.goForward();
  await assertHealthy(page, errors, `${label} voltar/avançar`);
  await context.close();
}

const browser = await chromium.launch(launch);
const run = async (opts) => {
  try {
    await tour(browser, opts);
  } catch (e) {
    failures.push(String(e.message ?? e));
  }
};
try {
  await run({
    label: "computador",
    viewport: { width: 1366, height: 900 },
    navSelector: "aside nav",
    names: { dashboard: "Painel", bots: "Bots", lab: "Laboratório", ai: "Análise IA", settings: "Configurações" },
  });
  await run({
    label: "celular",
    viewport: { width: 390, height: 844 },
    navSelector: 'nav[aria-label="Navegação principal"]',
    names: { dashboard: "Painel", bots: "Bots", lab: "Lab", ai: "IA", settings: "Ajustes" },
  });
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`\nFALHOU (${failures.length} problema(s) em ${steps} verificações):\n- ${failures.join("\n- ")}`);
  process.exit(1);
}
console.log(`e2e ok: ${steps} verificações, nenhum erro de tela ou de JavaScript`);
