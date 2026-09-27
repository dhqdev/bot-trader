// Recusa efeitos React que devolvem um valor sem querer.
//
// `useEffect(() => algo())` devolve o retorno de algo(). O React trata esse
// valor como a função de limpeza e o chama ao trocar de tela; se não for uma
// função, a tela quebra ("l is not a function"). Foi o que aconteceu com
// window.scrollTo, que no Chrome atual passou a devolver uma Promise.
// Regra: efeitos sempre com corpo entre chaves, e nunca `async`.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("../src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const BAD = [
  { re: /use(Layout)?Effect\(\s*\(\s*\)\s*=>(?!\s*\{)/g, why: "efeito com retorno implícito: use () => { ... }" },
  { re: /use(Layout)?Effect\(\s*async\b/g, why: "efeito async devolve uma Promise: chame uma função async dentro do efeito" },
];

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(tsx?|jsx?)$/.test(name) ? [path] : [];
  });
}

const problems = [];
for (const file of files(ROOT)) {
  const text = readFileSync(file, "utf8");
  for (const { re, why } of BAD) {
    for (const m of text.matchAll(re)) {
      const line = text.slice(0, m.index).split("\n").length;
      problems.push(`${file}:${line}: ${why}`);
    }
  }
}

if (problems.length) {
  console.error("Efeitos React inválidos:\n" + problems.join("\n"));
  process.exit(1);
}
console.log("check-effects: ok");
