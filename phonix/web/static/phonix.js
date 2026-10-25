/*
 * PhonixPBX UI glue (no inline scripts: the CSP only allows 'self').
 * - sends the CSRF token with every htmx request
 * - initialises Tabler-supported libraries (Tom Select, Autosize, IMask,
 *   Dropzone, ApexCharts, SortableJS) on page load and on htmx 4 swapped content
 * - small helpers driven by data-* attributes
 */
(function () {
  "use strict";

  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

  // ---- htmx 4 -----------------------------------------------------------------
  document.addEventListener("htmx:config:request", (evt) => {
    const ctx = evt.detail && evt.detail.ctx;
    if (ctx && ctx.request && ctx.request.headers) {
      ctx.request.headers["X-CSRF-Token"] = csrf();
    }
  });

  // destroy widgets inside elements htmx is about to remove
  document.addEventListener("htmx:before:cleanup", (evt) => teardown(evt.target));

  // ---- widget initialisation -------------------------------------------------------
  const charts = new WeakMap();

  function init(root) {
    root = root || document;
    const scope = (sel) => {
      const list = Array.from(root.querySelectorAll ? root.querySelectorAll(sel) : []);
      if (root.matches && root.matches(sel)) list.unshift(root);
      return list;
    };

    if (window.TomSelect) {
      scope("select[data-tom]").forEach((el) => {
        if (el.tomselect) return;
        // Tabler ships the "base" build of Tom Select (no plugins)
        try {
          const ts = new TomSelect(el, {
            create: el.hasAttribute("data-tom-create"),
            maxOptions: 500,
            allowEmptyOption: true,
            copyClassesToDropdown: false,
            dropdownParent: "body",
            render: { no_results: () => '<div class="no-results">No matches</div>' },
          });
          // data-tom-sortable: the chosen items can be dragged into order; the form posts them in that order
          if (el.hasAttribute("data-tom-sortable") && window.Sortable) {
            el._sortable = Sortable.create(ts.control, {
              draggable: ".item",
              animation: 150,
              // Tom Select cancels mousedown on its items, which stops a native HTML5 drag
              forceFallback: true,
              onEnd: () => {
                ts.items = Array.from(ts.control.querySelectorAll(".item"), (item) => item.dataset.value);
                ts.updateOriginalInput();
              },
            });
          }
        } catch (e) {
          console.warn("TomSelect", e);
        }
      });
    }

    if (window.autosize) autosize(scope("textarea[data-autosize]"));

    if (window.IMask) {
      const masks = {
        digits: { mask: /^\d*$/ },
        ipv4: {
          mask: "IP.IP.IP.IP",
          lazy: true,
          blocks: { IP: { mask: Number, scale: 0, min: 0, max: 255 } },
        },
        port: { mask: Number, min: 1, max: 65535, scale: 0 },
        dialcode: { mask: /^[0-9*#]*$/ },
      };
      scope("input[data-mask]").forEach((el) => {
        if (el._imask) return;
        const def = masks[el.dataset.mask];
        if (def) el._imask = IMask(el, def);
      });
    }

    if (window.Dropzone) {
      Dropzone.autoDiscover = false;
      // a <div data-dropzone data-url> can sit inside another form (forms cannot nest)
      scope("form[data-dropzone], div[data-dropzone]").forEach((form) => {
        if (form.dropzone) return;
        const dz = new Dropzone(form, {
          url: form.dataset.url || form.action,
          paramName: form.dataset.param || "file",
          maxFilesize: Number(form.dataset.maxMb || 512),
          acceptedFiles: form.dataset.accept || null,
          maxFiles: 1,
          timeout: 0,
          headers: { "X-CSRF-Token": csrf() },
          dictDefaultMessage: form.dataset.message || "Drop a file here or click to upload",
        });
        // data-requires="#checkbox": uploads stay disabled until it is ticked
        const gate = form.dataset.requires && document.querySelector(form.dataset.requires);
        if (gate) {
          const sync = () => {
            if (gate.checked) dz.enable();
            else dz.disable();
            form.classList.toggle("opacity-50", !gate.checked);
          };
          gate.addEventListener("change", sync);
          sync();
        }
        // data-uploading: a progress bar in the target while the bytes are sent (Dropzone's own
        // preview needs dropzone.css, which is not vendored)
        let bar = null;
        dz.on("sending", (file) => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (!target || !form.dataset.uploading) return;
          const note = document.createElement("div");
          note.className = "alert alert-info mt-3 mb-0";
          const head = document.createElement("div");
          head.className = "d-flex align-items-center mb-2";
          const label = document.createElement("strong");
          label.className = "text-truncate";
          label.textContent = `${form.dataset.uploading} ${file.name}`;
          const percent = document.createElement("span");
          percent.className = "ms-auto ps-2 text-secondary small";
          percent.textContent = "0 %";
          head.append(label, percent);
          const progress = document.createElement("div");
          progress.className = "progress progress-sm";
          const fill = document.createElement("div");
          fill.className = "progress-bar";
          fill.setAttribute("role", "progressbar");
          fill.style.width = "0%";
          progress.append(fill);
          note.append(head, progress);
          target.replaceChildren(note);
          bar = { fill, percent };
        });
        // the server answers only after it stored the file: say so once the bytes are sent
        dz.on("uploadprogress", (file, progress) => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (bar && progress < 100) {
            bar.fill.style.width = `${progress}%`;
            bar.percent.textContent = `${Math.floor(progress)} %`;
          }
          if (progress >= 100 && target && form.dataset.processing && !target.dataset.processing) {
            target.dataset.processing = "1";
            const note = document.createElement("div");
            note.className = "alert alert-info mt-3 mb-0 d-flex align-items-center";
            note.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>';
            note.append(form.dataset.processing);
            target.replaceChildren(note);
          }
        });
        dz.on("complete", () => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (target) delete target.dataset.processing;
          bar = null;
        });
        dz.on("success", (file, response) => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (target) {
            target.innerHTML = typeof response === "string" ? response : "";
            if (window.htmx) htmx.process(target);
            init(target);
          }
          if (form.dataset.reload) window.location.reload();
          dz.removeAllFiles();
          // data-hide-on-success: a one-shot upload (the result takes over, e.g. a running update)
          if ("hideOnSuccess" in form.dataset) {
            dz.disable();
            form.classList.add("d-none");
          }
        });
        dz.on("error", (file, message, xhr) => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (target && typeof message === "string" && message.trim().startsWith("<")) {
            target.innerHTML = message;
            dz.removeAllFiles();
          } else if (target && form.dataset.uploading) {
            // the preview with Dropzone's error is hidden: show it in the target
            const note = document.createElement("div");
            note.className = "alert alert-danger mt-3 mb-0";
            note.textContent = typeof message === "string" ? message : (message && message.error) || String(message);
            target.replaceChildren(note);
            dz.removeAllFiles();
          } else if (target && target.dataset.processing) {
            target.replaceChildren(); // the error is shown on the file
          }
        });
      });
    }

    if (window.ApexCharts) {
      scope("[data-chart]").forEach((el) => {
        if (charts.has(el)) return;
        const kind = el.dataset.chart;
        const options = chartOptions(kind, el);
        const chart = new ApexCharts(el, options);
        chart.render();
        charts.set(el, chart);
        if (el.dataset.chartUrl) pollChart(el, chart);
      });
    }

    // Tabler (Bootstrap) tooltips
    if (window.bootstrap && bootstrap.Tooltip) {
      scope('[data-bs-toggle="tooltip"]').forEach((el) => bootstrap.Tooltip.getOrCreateInstance(el));
    }
  }

  function teardown(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("select[data-tom]").forEach((el) => {
      if (el._sortable) {
        el._sortable.destroy();
        el._sortable = null;
      }
      if (el.tomselect) el.tomselect.destroy();
    });
    root.querySelectorAll("[data-chart]").forEach((el) => {
      const c = charts.get(el);
      if (c) {
        clearInterval(el._poll);
        c.destroy();
        charts.delete(el);
      }
    });
  }

  // ---- charts ---------------------------------------------------------------------
  const css = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

  function bytes(v) {
    const units = ["B/s", "KB/s", "MB/s", "GB/s"];
    let i = 0;
    while (Math.abs(v) >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    return v.toFixed(i ? 1 : 0) + " " + units[i];
  }

  function chartOptions(kind, el) {
    const primary = css("--phonix-primary", "#435370");
    const accent = css("--phonix-accent", "#687ba4");
    const base = {
      chart: {
        type: "area",
        height: Number(el.dataset.height || 240),
        fontFamily: "inherit",
        animations: { enabled: false },
        toolbar: { show: false },
        zoom: { enabled: false },
        sparkline: { enabled: el.dataset.sparkline === "1" },
      },
      dataLabels: { enabled: false },
      stroke: { width: 2, curve: "smooth" },
      fill: { opacity: 0.16, type: "solid" },
      grid: { strokeDashArray: 4 },
      xaxis: { type: "datetime", labels: { datetimeUTC: false } },
      tooltip: { theme: document.documentElement.dataset.bsTheme === "dark" ? "dark" : "light", x: { format: "HH:mm:ss" } },
      legend: { show: true, position: "top" },
      noData: { text: "collecting data..." },
      colors: [primary, accent],
      series: [],
    };
    if (kind === "cpu") {
      base.yaxis = { min: 0, max: 100, labels: { formatter: (v) => v.toFixed(0) + " %" } };
      base.series = [{ name: "CPU", data: [] }];
    } else if (kind === "network") {
      base.yaxis = { labels: { formatter: bytes } };
      base.series = [{ name: "in", data: [] }, { name: "out", data: [] }];
    }
    return base;
  }

  function pollChart(el, chart) {
    const load = () =>
      fetch(el.dataset.chartUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data) return;
          if (el.dataset.chart === "cpu") {
            chart.updateSeries([{ name: "CPU", data: data.map((s) => [s.ts * 1000, s.cpu]) }]);
          } else {
            chart.updateSeries([
              { name: "in", data: data.map((s) => [s.ts * 1000, s.rx]) },
              { name: "out", data: data.map((s) => [s.ts * 1000, s.tx]) },
            ]);
          }
        })
        .catch(() => {});
    load();
    el._poll = setInterval(() => {
      if (!document.body.contains(el)) return clearInterval(el._poll);
      load();
    }, Number(el.dataset.interval || 3000));
  }

  // ---- data-* helpers ---------------------------------------------------------------
  document.addEventListener("click", (evt) => {
    const gen = evt.target.closest("[data-generate-secret]");
    if (gen) {
      const input = document.querySelector(gen.dataset.generateSecret);
      if (input) {
        const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
        const buf = new Uint32Array(16);
        crypto.getRandomValues(buf);
        input.value = Array.from(buf, (x) => alphabet[x % alphabet.length]).join("");
        input.type = "text";
      }
      return;
    }
    // <button data-copy="#input">: copy the input's value to the clipboard
    const copy = evt.target.closest("[data-copy]");
    if (copy) {
      const input = document.querySelector(copy.dataset.copy);
      if (input) {
        input.select();
        if (navigator.clipboard) navigator.clipboard.writeText(input.value).catch(() => {});
        copy.textContent = copy.dataset.copied || "Copied";
      }
      return;
    }
    const toggle = evt.target.closest("[data-toggle-password]");
    if (toggle) {
      const input = document.querySelector(toggle.dataset.togglePassword);
      if (input) input.type = input.type === "password" ? "text" : "password";
      return;
    }
    // dynamic rows: <button data-add-row="#template" data-into="#container">
    const add = evt.target.closest("[data-add-row]");
    if (add) {
      const tpl = document.querySelector(add.dataset.addRow);
      const into = document.querySelector(add.dataset.into);
      if (tpl && into) {
        const index = Date.now().toString(36);
        const html = tpl.innerHTML.replaceAll("__INDEX__", index);
        into.insertAdjacentHTML("beforeend", html);
        const row = into.lastElementChild;
        // <select data-unique="group">: preselect the first value no other row of the group uses
        row.querySelectorAll("select[data-unique]").forEach((sel) => {
          const others = into.querySelectorAll(`select[data-unique="${sel.dataset.unique}"]`);
          const used = new Set(Array.from(others, (o) => (o === sel ? null : o.value)));
          const free = Array.from(sel.options).find((o) => !used.has(o.value));
          if (free) sel.value = free.value;
        });
        init(row);
        if (window.htmx) htmx.process(row);
      }
      return;
    }
    // reorder with the keyboard / without drag and drop: <button data-move="up|down">
    const move = evt.target.closest("[data-move]");
    if (move) {
      const item = move.closest("[data-sortable-item]");
      if (item) {
        if (move.dataset.move === "up" && item.previousElementSibling) {
          item.parentElement.insertBefore(item, item.previousElementSibling);
        } else if (move.dataset.move === "down" && item.nextElementSibling) {
          item.parentElement.insertBefore(item.nextElementSibling, item);
        }
        move.focus();
      }
      return;
    }
    const remove = evt.target.closest("[data-remove-row]");
    if (remove) {
      const row = remove.closest(".dyn-row");
      if (row) {
        teardown(row);
        row.remove();
      }
      return;
    }
    const print = evt.target.closest("[data-print]");
    if (print) window.print();
  });

  // show/hide dependent form parts: <div data-show-if="name=value">
  function updateConditional(form) {
    form.querySelectorAll("[data-show-if]").forEach((el) => {
      const [name, expected] = el.dataset.showIf.split("=");
      const field = form.querySelector(`[name="${name}"]:checked, select[name="${name}"], input[type=hidden][name="${name}"]`);
      let value = "";
      if (field) value = field.type === "checkbox" ? (field.checked ? "true" : "false") : field.value;
      const cb = form.querySelector(`input[type=checkbox][name="${name}"]`);
      if (cb) value = cb.checked ? "true" : "false";
      const ok = expected.split("|").includes(value);
      el.hidden = !ok;
    });
    // <label data-show-if-filled="selector">: shown while every matching field of its row has a value;
    // its checkboxes are cleared while hidden
    form.querySelectorAll("[data-show-if-filled]").forEach((el) => {
      const row = el.closest(".dyn-row") || form;
      const fields = Array.from(row.querySelectorAll(el.dataset.showIfFilled));
      el.hidden = !fields.every((f) => f.value);
      if (el.hidden) el.querySelectorAll("input[type=checkbox]").forEach((cb) => (cb.checked = false));
    });
  }
  document.addEventListener("change", (evt) => {
    const form = evt.target.closest("form");
    if (form) updateConditional(form);
    // <select data-submit-on-change>: e.g. a language switch of a GET form
    if (form && evt.target.closest("[data-submit-on-change]")) form.requestSubmit();
  });

  // keep the log view scrolled to the end when new lines arrive
  document.addEventListener("htmx:after:swap", (evt) => {
    const log = evt.target.closest ? evt.target.closest("[data-autoscroll]") : null;
    if (log) log.scrollTop = log.scrollHeight;
  });

  // after a reboot: wait until the system went away and came back, then go to data-next
  function watchReboot(el) {
    const status = document.querySelector("[data-reboot-status]");
    const say = (text) => {
      if (status && text) status.textContent = text;
    };
    const next = el.dataset.next || "/";
    const started = Date.now();
    let wentDown = false;
    let up = 0;
    const down = () => {
      if (!wentDown) say(el.dataset.textDown);
      wentDown = true;
      up = 0;
    };
    const tick = () => {
      if (Date.now() - started > 600000) say(el.dataset.textSlow);
      fetch(el.dataset.reloadWhenUp, { cache: "no-store", credentials: "same-origin" })
        .then((r) => {
          // 502/503 while nginx is up but the web app still starts
          if (!r.ok) return down();
          // twice in a row: the app answers, not just a service that is still starting
          if (wentDown) up += 1;
          if (up >= 2 || (!wentDown && Date.now() - started > 120000)) window.location.href = next;
        })
        .catch(down);
    };
    setInterval(tick, 5000);
  }

  // tabs as links: /page#tab-x opens that tab, and the address follows the open tab
  function openTabFromHash() {
    if (!location.hash.startsWith("#tab-")) return;
    const link = document.querySelector(`[data-bs-toggle="tab"][href="${CSS.escape(location.hash)}"]`);
    if (link && !link.classList.contains("active")) link.click();
  }
  // and elements in the tab whose hx-trigger has phonix:tab-shown reload, e.g. a preview of the form
  document.addEventListener("shown.bs.tab", (evt) => {
    const href = evt.target.getAttribute("href");
    if (!href || !href.startsWith("#tab-")) return;
    history.replaceState(null, "", href);
    document.getElementById(href.slice(1))?.querySelectorAll('[hx-trigger*="phonix:tab-shown"]')
      .forEach((el) => el.dispatchEvent(new CustomEvent("phonix:tab-shown")));
  });

  function ready() {
    openTabFromHash();
    document.querySelectorAll("[data-reload-when-up]").forEach(watchReboot);
    init(document);
    document.querySelectorAll("form").forEach(updateConditional);
    document.querySelectorAll("[data-autoscroll]").forEach((el) => (el.scrollTop = el.scrollHeight));
    if (window.htmx && htmx.onLoad) {
      htmx.onLoad((elt) => {
        init(elt);
        const form = elt.closest ? elt.closest("form") : null;
        if (form) updateConditional(form);
      });
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else ready();
})();
