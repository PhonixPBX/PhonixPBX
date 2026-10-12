/*
 * AskoziaPBX UI glue (no inline scripts: the CSP only allows 'self').
 * - sends the CSRF token with every htmx request
 * - initialises Tabler-supported libraries (Tom Select, Autosize, IMask,
 *   Dropzone, ApexCharts) on page load and on htmx 4 swapped content
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
          new TomSelect(el, {
            create: el.hasAttribute("data-tom-create"),
            maxOptions: 500,
            allowEmptyOption: true,
            copyClassesToDropdown: false,
            dropdownParent: "body",
            render: { no_results: () => '<div class="no-results">No matches</div>' },
          });
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
      scope("form[data-dropzone]").forEach((form) => {
        if (form.dropzone) return;
        const dz = new Dropzone(form, {
          paramName: form.dataset.param || "file",
          maxFilesize: Number(form.dataset.maxMb || 512),
          acceptedFiles: form.dataset.accept || null,
          maxFiles: 1,
          timeout: 0,
          headers: { "X-CSRF-Token": csrf() },
          dictDefaultMessage: form.dataset.message || "Drop a file here or click to upload",
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
        });
        dz.on("error", (file, message, xhr) => {
          const target = document.querySelector(form.dataset.target || "#upload-result");
          if (target && typeof message === "string" && message.trim().startsWith("<")) {
            target.innerHTML = message;
            dz.removeAllFiles();
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
    root.querySelectorAll("select[data-tom]").forEach((el) => el.tomselect && el.tomselect.destroy());
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
    const primary = css("--askozia-primary", "#435370");
    const accent = css("--askozia-accent", "#687ba4");
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
        init(row);
        if (window.htmx) htmx.process(row);
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
  }
  document.addEventListener("change", (evt) => {
    const form = evt.target.closest("form");
    if (form) updateConditional(form);
  });

  // keep the log view scrolled to the end when new lines arrive
  document.addEventListener("htmx:after:swap", (evt) => {
    const log = evt.target.closest ? evt.target.closest("[data-autoscroll]") : null;
    if (log) log.scrollTop = log.scrollHeight;
  });

  // after a reboot: wait until the system went away and came back, then reload
  function watchReboot(el) {
    let wentDown = false;
    const started = Date.now();
    const tick = () =>
      fetch(el.dataset.reloadWhenUp, { cache: "no-store", credentials: "same-origin" })
        .then((r) => {
          if (r.ok && (wentDown || Date.now() - started > 120000)) window.location.href = "/";
        })
        .catch(() => (wentDown = true));
    setInterval(tick, 5000);
  }

  function ready() {
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
