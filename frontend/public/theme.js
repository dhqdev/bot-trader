// Aplica o tema salvo antes da tela aparecer (evita piscar claro/escuro).
// Fica num arquivo separado porque a política de segurança (CSP) não permite scripts dentro do HTML.
try {
  var t = localStorage.getItem("bt-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  if (t === "light") document.querySelector('meta[name="theme-color"]').setAttribute("content", "#f9f9f7");
} catch (e) {
  /* armazenamento bloqueado: fica o tema padrão */
}
