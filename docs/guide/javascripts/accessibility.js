// 2.1.1 Keyboard: a table wider than the page scrolls inside its wrapper, so the wrapper takes
// focus and a keyboard user can scroll it with the arrow keys. The theme does this for code
// blocks but not for tables. `document$` is the theme's page-load observable, which also fires
// after instant navigation.
document$.subscribe(() => {
  for (const wrap of document.querySelectorAll(".md-typeset__scrollwrap")) {
    if (wrap.scrollWidth > wrap.clientWidth) {
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Table, scrolls sideways");
    }
  }
});
