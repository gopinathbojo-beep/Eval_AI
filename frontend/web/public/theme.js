(function () {
  var pref = "system";
  try { pref = localStorage.getItem("adem_theme") || "system"; } catch (e) {}
  var dark = pref === "dark" || (pref !== "light" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.setAttribute("data-theme", dark ? "dark" : "light");
  root.style.colorScheme = dark ? "dark" : "light";
})();
