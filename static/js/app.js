/* Helpdesk N1 — comportements de l'interface (aucune dépendance). */
(function () {
  "use strict";

  /* ------------------------------------------------ lignes de règle dépliables */
  var disclosures = document.querySelectorAll("[data-disclosure]");
  Array.prototype.forEach.call(disclosures, function (button) {
    var target = document.getElementById(button.getAttribute("aria-controls"));
    if (!target) { return; }
    button.addEventListener("click", function () {
      var open = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", open ? "false" : "true");
      target.hidden = open;
    });
  });

  /* ---------------------------------------------------------------- impression */
  var printButtons = document.querySelectorAll("[data-print]");
  Array.prototype.forEach.call(printButtons, function (button) {
    button.addEventListener("click", function () { window.print(); });
  });

  var closeButtons = document.querySelectorAll("[data-close]");
  Array.prototype.forEach.call(closeButtons, function (button) {
    button.addEventListener("click", function () { window.close(); });
  });

  /* ---------------------------------------------------- copie de la procédure */
  var copyBtn = document.getElementById("copy-procedure-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var container = document.getElementById("procedure-steps-container");
      if (!container) { return; }
      var items = container.querySelectorAll(".step__text, li, p");
      var text = [];
      Array.prototype.forEach.call(items, function (el, idx) {
        var t = el.textContent.trim();
        if (t && text.indexOf(t) === -1) {
          text.push((text.length + 1) + ". " + t);
        }
      });
      var fullText = text.length ? text.join("\n") : container.textContent.trim();
      navigator.clipboard.writeText(fullText).then(function () {
        var old = copyBtn.innerHTML;
        copyBtn.innerHTML = "Copié !";
        copyBtn.classList.add("btn--primary");
        setTimeout(function () {
          copyBtn.innerHTML = old;
          copyBtn.classList.remove("btn--primary");
        }, 1800);
      });
    });
  }

  /* ------------------------------------------------------------------ benchmark */
  var form = document.getElementById("bench-form");
  if (!form) { return; }

  var runButton = document.getElementById("bench-run");
  var label = runButton ? runButton.querySelector(".btn__label") : null;
  var status = document.getElementById("bench-status");
  var empty = document.getElementById("bench-empty");
  var bars = document.getElementById("bench-bars");
  var tableHost = document.getElementById("bench-table");
  var note = document.getElementById("bench-note");

  function format(value) {
    return Number(value).toFixed(1);
  }

  function setStatus(message, isError) {
    if (!status) { return; }
    status.textContent = message;
    status.style.color = isError ? "var(--danger)" : "";
  }

  function busy(state) {
    if (!runButton) { return; }
    runButton.disabled = state;
    runButton.classList.toggle("is-loading", state);
    if (label) {
      label.textContent = state ? "Calcul en cours…" : "Relancer le benchmark";
    }
  }

  function renderBars(results) {
    bars.textContent = "";
    results.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "bench__row" + (item.model === "Système expert" ? " bench__row--expert" : "");

      var name = document.createElement("div");
      name.className = "bench__name";
      var strong = document.createElement("strong");
      strong.textContent = item.model;
      var sub = document.createElement("span");
      sub.textContent = "min " + format(item.min) + " · max " + format(item.max);
      name.appendChild(strong);
      name.appendChild(sub);

      var track = document.createElement("div");
      track.className = "bench__track";
      var fill = document.createElement("div");
      fill.className = "bench__fill";
      fill.style.width = "0%";
      track.appendChild(fill);

      var value = document.createElement("div");
      value.className = "bench__value";
      value.appendChild(document.createTextNode(format(item.mean) + " %"));
      var caption = document.createElement("small");
      caption.textContent = "moyenne";
      value.appendChild(caption);

      row.appendChild(name);
      row.appendChild(track);
      row.appendChild(value);
      bars.appendChild(row);

      var width = Math.max(0, Math.min(100, Number(item.mean)));
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () { fill.style.width = width + "%"; });
      });
    });
  }

  function renderTable(results) {
    var table = document.createElement("table");
    table.className = "table";

    var caption = document.createElement("caption");
    caption.className = "sr-only";
    caption.textContent = "Précision moyenne, minimale et maximale par modèle sur dix tirages.";
    table.appendChild(caption);

    var head = document.createElement("thead");
    var headRow = document.createElement("tr");
    ["Modèle", "Précision moyenne", "Minimum", "Maximum"].forEach(function (text) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = text;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);

    var body = document.createElement("tbody");
    results.forEach(function (item) {
      var tr = document.createElement("tr");
      [item.model, format(item.mean) + " %", format(item.min) + " %", format(item.max) + " %"]
        .forEach(function (text, index) {
          var td = document.createElement("td");
          td.textContent = text;
          if (index > 0) { td.className = "num"; }
          td.setAttribute("data-label", ["Modèle", "Moyenne", "Minimum", "Maximum"][index]);
          tr.appendChild(td);
        });
      body.appendChild(tr);
    });
    table.appendChild(body);

    tableHost.textContent = "";
    tableHost.appendChild(table);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (runButton && runButton.disabled) { return; }

    busy(true);
    setStatus("Génération de 300 tickets bruités sur 10 tirages. Cela prend quelques secondes…", false);
    if (empty) { empty.hidden = true; }

    window.fetch(form.getAttribute("action"), {
      method: "POST",
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          throw new Error(data && data.error ? data.error : "Le calcul du benchmark a échoué.");
        }
        return data;
      });
    }).then(function (data) {
      if (!data.results || !data.results.length) {
        throw new Error("Aucun résultat renvoyé par le serveur.");
      }
      renderBars(data.results);
      renderTable(data.results);
      bars.hidden = false;
      tableHost.hidden = false;
      if (note) { note.hidden = false; }
      setStatus("Résultats disponibles" + (data.cached ? " (calcul mis en cache pour cette session)." : "."), false);
    }).catch(function (error) {
      if (empty) {
        empty.hidden = false;
        empty.querySelector("span").textContent = "Le calcul n'a pas abouti : " + error.message + " Vous pouvez relancer.";
      }
      if (bars) { bars.hidden = true; }
      if (tableHost) { tableHost.hidden = true; }
      if (note) { note.hidden = true; }
      setStatus("Échec du benchmark : " + error.message, true);
    }).finally(function () {
      busy(false);
    });
  });
}());
