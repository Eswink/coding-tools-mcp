/* Gateway Ops Console UI — FR-UI switches/selects; secrets never posted as inline values. */
(function () {
  const HDR = { "Content-Type": "application/json", "X-Ops-Console": "1" };

  async function api(method, url, body) {
    const opts = { method, headers: method === "GET" ? {} : HDR };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { ok: false, error: "invalid_json", raw: text }; }
    return { status: res.status, data };
  }

  function show(el, obj) {
    el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  }

  const fields = [
    "origin", "prefix", "connector", "owner_subject",
    "client_id", "redirect_uri", "client_authentication", "bind"
  ];

  function readForm() {
    const data = {};
    for (const k of fields) {
      const el = document.getElementById("f-" + k);
      if (el) data[k] = el.value;
    }
    return data;
  }

  function fillForm(data) {
    for (const k of fields) {
      const el = document.getElementById("f-" + k);
      if (el && data && data[k] != null) el.value = data[k];
    }
  }

  document.getElementById("btn-load").addEventListener("click", async () => {
    const { data } = await api("GET", "/api/v1/config?path=config.json");
    show(document.getElementById("config-out"), data);
    if (data && data.ok) fillForm(data.data || {});
  });

  document.getElementById("config-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const ack = document.getElementById("f-no-secrets-ack");
    if (!ack.checked) {
      show(document.getElementById("config-out"), { ok: false, error: "请先勾选：不在此表单填写任何密钥" });
      return;
    }
    const { data } = await api("PUT", "/api/v1/config?path=config.json", { data: readForm() });
    show(document.getElementById("config-out"), data);
  });

  document.getElementById("btn-kit-plan").addEventListener("click", async () => {
    const { data } = await api("POST", "/api/v1/kit/preview", { action: "plan" });
    show(document.getElementById("kit-out"), data);
  });

  document.getElementById("btn-kit-render").addEventListener("click", async () => {
    const { data } = await api("POST", "/api/v1/kit/preview", {
      action: "render_diff",
      private_root_rel: ".",
      options: {}
    });
    show(document.getElementById("kit-out"), data);
  });

  async function cli(path) {
    const body = {
      config_rel: document.getElementById("cli-config-rel").value || "config.json",
      secrets_file_rel: document.getElementById("cli-secrets-rel").value || undefined,
      output_rel: document.getElementById("cli-output-rel").value || undefined
    };
    const { data } = await api("POST", path, body);
    show(document.getElementById("cli-out"), data);
  }

  document.getElementById("btn-check").addEventListener("click", () => cli("/api/v1/cli/check-config"));
  document.getElementById("btn-register").addEventListener("click", () => cli("/api/v1/cli/register-client"));
  document.getElementById("btn-invite").addEventListener("click", () => cli("/api/v1/cli/invite-device"));

  document.getElementById("btn-devices").addEventListener("click", async () => {
    const { data } = await api("GET", "/api/v1/devices/local");
    show(document.getElementById("devices-out"), data);
  });

  api("GET", "/api/v1/health").then(({ data }) => {
    document.getElementById("health").textContent =
      data && data.ok
        ? `健康：${data.service} @ ${data.bind}`
        : `健康检查失败：${JSON.stringify(data)}`;
  });
})();
