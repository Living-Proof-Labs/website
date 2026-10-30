// SPDX-License-Identifier: Apache-2.0
// Compact mobile menu. Without JavaScript the full nav stays visible and the header is not sticky on small screens.
(function () {
  var header = document.querySelector(".site-header");
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("primary-nav");
  if (!header || !toggle || !nav) return;
  header.classList.add("has-menu");
  toggle.hidden = false;
  function setOpen(open) {
    toggle.setAttribute("aria-expanded", String(open));
    header.classList.toggle("menu-open", open);
  }
  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });
  nav.addEventListener("click", function (event) {
    if (event.target.closest("a")) setOpen(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && header.classList.contains("menu-open")) {
      setOpen(false);
      toggle.focus();
    }
  });
})();
