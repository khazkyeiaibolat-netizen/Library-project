/* Small progressive enhancements. The site still works without JavaScript. */
(function () {
  "use strict";

  // mobile navigation
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // confirm before destructive actions: <form data-confirm="Are you sure?">
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-toggle-password"));
      input.type = input.type === "password" ? "text" : "password";
    });
  });

  // chart bars (widths come from data attributes so the page needs no inline scripts)
  document.querySelectorAll("[data-w]").forEach(function (el) { el.style.width = el.getAttribute("data-w") + "%"; });
  document.querySelectorAll("[data-h]").forEach(function (el) { el.style.height = el.getAttribute("data-h") + "%"; });

  // filter a <select> as you type
  document.querySelectorAll("[data-filter-select]").forEach(function (input) {
    var select = document.getElementById(input.getAttribute("data-filter-select"));
    var all = Array.prototype.slice.call(select.options);
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var keep = all.filter(function (o) { return !o.value || o.text.toLowerCase().indexOf(q) !== -1 || o.selected; });
      select.innerHTML = "";
      keep.forEach(function (o) { select.appendChild(o); });
      if (q && keep.length === 2) select.selectedIndex = 1;
    });
  });

  // issue form: reload the list of books in stock when the branch changes
  var form = document.getElementById("issue-form");
  if (form) {
    var branch = document.getElementById("branch_id");
    var book = document.getElementById("book_id");
    var api = form.getAttribute("data-api");
    branch.addEventListener("change", function () {
      fetch(api.replace("/0/", "/" + branch.value + "/"), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (items) {
          var first = book.options[0].text;
          book.innerHTML = "";
          var o = document.createElement("option"); o.value = ""; o.text = first; book.appendChild(o);
          items.forEach(function (b) {
            var opt = document.createElement("option");
            opt.value = b.book_id;
            opt.text = b.title + " — " + b.author.split(",")[0] + " (" + b.quantity + ")";
            book.appendChild(opt);
          });
        });
    });
  }

  // admin form: show only the fields that belong to the chosen role
  var role = document.querySelector("[data-role-select]");
  if (role) {
    var sync = function () {
      document.querySelectorAll("[data-for-role]").forEach(function (el) {
        el.hidden = el.getAttribute("data-for-role") !== role.value;
      });
    };
    role.addEventListener("change", sync); sync();
  }

  // flash messages fade out
  document.querySelectorAll(".flash-success").forEach(function (el) {
    setTimeout(function () { el.classList.add("fade"); }, 4500);
  });
})();
