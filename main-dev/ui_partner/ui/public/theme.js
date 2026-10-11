// Set the theme before first paint: the saved choice, else Warm.
// An address may name one (#/...?theme=warm): that one is shown and saved.
(function () {
  var known = { warm: 1, light: 1, dark: 1 };
  var t = null;
  var named = /[?&]theme=([a-z]+)/.exec(location.hash);
  try {
    if (named && known[named[1]]) localStorage.setItem("theme", named[1]);
    t = localStorage.getItem("theme");
  } catch (e) {
    t = named ? named[1] : null;
  }
  if (!known[t]) t = "warm";
  document.documentElement.setAttribute("data-theme", t);
})();
