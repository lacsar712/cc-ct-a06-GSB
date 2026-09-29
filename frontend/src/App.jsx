import { createSignal, onMount, Show, For, createEffect } from "solid-js";
import {
  clearSession,
  correctSubmission,
  createSubmission,
  fetchHistory,
  fetchRange,
  fetchSubmission,
  fetchSubmissions,
  getUser,
  login,
  setSession,
  updateRange,
} from "./api";

const statusLabel = {
  pending: "待复核",
  processing: "复核中",
  done: "已完成",
};

const roleLabel = {
  machinist: "操作员",
  auditor: "复核员",
};

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "") || "/";
  const m = raw.match(/^\/detail\/(\d+)/);
  if (m) return { name: "detail", id: Number(m[1]) };
  if (raw === "/range") return { name: "range", id: null };
  return { name: "home", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [detail, setDetail] = createSignal(null);
  const [range, setRange] = createSignal(null);
  const [history, setHistory] = createSignal([]);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [notice, setNotice] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  const [toolCode, setToolCode] = createSignal("");
  const [offsetRaw, setOffsetRaw] = createSignal("");
  const [rangeLower, setRangeLower] = createSignal("");
  const [rangeUpper, setRangeUpper] = createSignal("");
  const [correctRaw, setCorrectRaw] = createSignal("");

  function goHome() {
    location.hash = "#/";
  }

  function goRange() {
    location.hash = "#/range";
  }

  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  function flash(message) {
    setNotice(message);
    setError("");
  }

  async function loadRows() {
    setLoading(true);
    try {
      setRows(await fetchSubmissions());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id) {
    setLoading(true);
    try {
      setDetail(await fetchSubmission(id));
      setCorrectRaw("");
    } catch (e) {
      setError(e.message);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadRange() {
    try {
      const data = await fetchRange();
      setRange(data);
      setRangeLower(String(data.lower_limit));
      setRangeUpper(String(data.upper_limit));
    } catch (e) {
      setError(e.message);
    }
  }

  async function loadHistory() {
    try {
      setHistory(await fetchHistory());
    } catch (e) {
      setError(e.message);
    }
  }

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    setError("");
    setNotice("");
    if (r.name === "detail" && r.id) loadDetail(r.id);
    if (r.name === "home") loadRows();
    if (r.name === "range") {
      loadRange();
      loadHistory();
    }
  });

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await login(loginUser(), loginPass());
      setSession(data.token, {
        username: data.username,
        role: data.role,
        can_write: data.can_write,
      });
      setUser(getUser());
      goHome();
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setRows([]);
    setDetail(null);
    setRange(null);
    setHistory([]);
    goHome();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    try {
      // 表单入口：越界时后端按同一套区间规则退回并说明原因
      await createSubmission(toolCode(), offsetRaw());
      setToolCode("");
      setOffsetRaw("");
      flash("交单成功，刀补原文已记入履历");
      await loadHistory();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSaveRange(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    try {
      const data = await updateRange(Number(rangeLower()), Number(rangeUpper()));
      setRange(data);
      flash(`量程区间已更新为闭区间 [${data.lower_limit}, ${data.upper_limit}] 微米`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCorrect(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    const d = detail();
    try {
      // 改正只动单据数字，履历旧值保持不动
      const updated = await correctSubmission(d.id, correctRaw());
      setDetail(updated);
      setCorrectRaw("");
      flash("单据数字已改正，交单履历旧值保持不变；可到量程台履历区对照验收");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补复核台</h1>
          <p class="hint">
            刀补数值只能落在量程台设定的闭区间内；每次成功交单把当时刀补原文记入履历，事后改正单据不动履历旧值。
          </p>
        </div>
        <Show when={user()}>
          <nav class="topnav">
            <a
              href="#/"
              class={route().name === "home" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goHome();
              }}
            >
              复核总览
            </a>
            <a
              href="#/range"
              class={route().name === "range" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goRange();
              }}
            >
              量程台
            </a>
          </nav>
        </Show>
      </header>

      <Show when={error()}>
        <div class="banner error">{error()}</div>
      </Show>
      <Show when={notice()}>
        <div class="banner ok">{notice()}</div>
      </Show>

      <Show
        when={user()}
        fallback={
          <section class="card">
            <h2>登录</h2>
            <form onSubmit={handleLogin} class="form">
              <label>
                用户名
                <input
                  value={loginUser()}
                  onInput={(e) => setLoginUser(e.currentTarget.value)}
                />
              </label>
              <label>
                密码
                <input
                  type="password"
                  value={loginPass()}
                  onInput={(e) => setLoginPass(e.currentTarget.value)}
                />
              </label>
              <button type="submit">进入系统</button>
            </form>
            <p class="hint">操作员 machinist / machine123456；复核员 auditor / audit123456（只读）</p>
          </section>
        }
      >
        <section class="card toolbar">
          <div>
            当前用户：<strong>{user().username}</strong>（{roleLabel[user().role] || user().role}）
          </div>
          <button type="button" class="ghost" onClick={handleLogout}>
            退出
          </button>
        </section>

        <Show when={route().name === "home"}>
          <section class="card">
            <div class="toolbar">
              <h2>复核列表</h2>
              <button type="button" class="ghost" onClick={loadRows} disabled={loading()}>
                {loading() ? "刷新中…" : "刷新"}
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>刀具</th>
                  <th>单据刀补 µm</th>
                  <th>状态</th>
                  <th>结论</th>
                  <th>提交时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr>
                      <td>{row.tool_code}</td>
                      <td>{row.offset_raw ? row.offset_raw : row.offset_um}</td>
                      <td>{statusLabel[row.status] || row.status}</td>
                      <td class={row.verdict === "合格" ? "pass" : row.verdict === "超差" ? "fail" : ""}>
                        {row.verdict || "—"}
                      </td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>
                        <button type="button" class="ghost" onClick={() => goDetail(row.id)}>
                          详情
                        </button>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!rows().length && !loading()}>
              <p class="hint">暂无记录，请到「量程台」交单。</p>
            </Show>
          </section>
        </Show>

        <Show when={route().name === "range"}>
          <section class="card">
            <h2>区间设置</h2>
            <Show when={range()} fallback={<p class="hint">加载中…</p>}>
              {(r) => (
                <>
                  <p class="hint">{r().rule_text}</p>
                  <Show
                    when={user().can_write}
                    fallback={
                      <p class="hint">
                        当前为复核员账号：可查看区间 [{r().lower_limit}, {r().upper_limit}] 微米，
                        但不能修改上下限。
                      </p>
                    }
                  >
                    <form onSubmit={handleSaveRange} class="form inline">
                      <label>
                        下限（微米，含）
                        <input
                          type="number"
                          value={rangeLower()}
                          onInput={(e) => setRangeLower(e.currentTarget.value)}
                          required
                        />
                      </label>
                      <label>
                        上限（微米，含）
                        <input
                          type="number"
                          value={rangeUpper()}
                          onInput={(e) => setRangeUpper(e.currentTarget.value)}
                          required
                        />
                      </label>
                      <button type="submit">保存区间</button>
                    </form>
                  </Show>
                  <p class="hint">
                    最近设置人：{r().updated_by || "系统默认"}
                  </p>
                </>
              )}
            </Show>
          </section>

          <section class="card">
            <h2>交单栏</h2>
            <Show when={user().can_write} fallback={<p class="hint">复核员只读，不能交单。</p>}>
              <form onSubmit={handleSubmit} class="form inline">
                <label>
                  刀具编号
                  <input
                    placeholder="如 T01"
                    value={toolCode()}
                    onInput={(e) => setToolCode(e.currentTarget.value)}
                    required
                  />
                </label>
                <label>
                  刀补原文（微米，整数）
                  <input
                    type="number"
                    value={offsetRaw()}
                    onInput={(e) => setOffsetRaw(e.currentTarget.value)}
                    required
                  />
                </label>
                <button type="submit">交单</button>
              </form>
            </Show>
          </section>

          <section class="card">
            <div class="toolbar">
              <h2>履历区</h2>
              <button type="button" class="ghost" onClick={loadHistory}>
                刷新
              </button>
            </div>
            <p class="hint">
              每条为成功交单当时的刀补原文，永不修改；与「单据当前值」并排可对照验收。
            </p>
            <table>
              <thead>
                <tr>
                  <th>交单时间</th>
                  <th>刀具</th>
                  <th>履历原文 µm</th>
                  <th>单据当前值 µm</th>
                  <th>对照</th>
                  <th>交单人</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <For each={history()}>
                  {(h) => (
                    <tr class={h.amended ? "row-amended" : ""}>
                      <td>{new Date(h.created_at).toLocaleString()}</td>
                      <td>{h.tool_code}</td>
                      <td>{h.offset_raw}</td>
                      <td>{h.current_offset_raw}</td>
                      <td class={h.amended ? "fail" : "pass"}>
                        {h.amended ? "已改正（旧值保留）" : "一致"}
                      </td>
                      <td>{h.submitted_by || "—"}</td>
                      <td>
                        <button
                          type="button"
                          class="ghost"
                          onClick={() => goDetail(h.submission_id)}
                        >
                          单据
                        </button>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!history().length}>
              <p class="hint">暂无履历</p>
            </Show>
          </section>
        </Show>

        <Show when={route().name === "detail"}>
          <section class="card">
            <div class="toolbar">
              <h2>刀补详情</h2>
              <button type="button" class="ghost" onClick={goHome}>
                返回总览
              </button>
            </div>
            <Show when={detail()} fallback={<p class="hint">{loading() ? "加载中…" : "未找到记录"}</p>}>
              {(d) => (
                <>
                  <div class="detail-grid">
                    <p>编号：{d().id}</p>
                    <p>刀具：{d().tool_code}</p>
                    <p>单据当前刀补 µm：{d().offset_raw ? d().offset_raw : d().offset_um}</p>
                    <p>状态：{statusLabel[d().status] || d().status}</p>
                    <p class={d().verdict === "合格" ? "pass" : d().verdict === "超差" ? "fail" : ""}>
                      结论：{d().verdict || "—"}
                    </p>
                    <p>提交时间：{new Date(d().created_at).toLocaleString()}</p>
                    <p>
                      复核时间：
                      {d().reviewed_at ? new Date(d().reviewed_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  <Show when={user().can_write}>
                    <form onSubmit={handleCorrect} class="form inline amend">
                      <label>
                        改正单据数字（微米，整数）
                        <input
                          type="number"
                          value={correctRaw()}
                          onInput={(e) => setCorrectRaw(e.currentTarget.value)}
                          required
                        />
                      </label>
                      <button type="submit">改正并重新复核</button>
                    </form>
                    <p class="hint">
                      改正只更新本单据并重新进入待复核；交单履历中的旧原文不会被改动，可到量程台对照。
                    </p>
                  </Show>
                </>
              )}
            </Show>
          </section>
        </Show>
      </Show>
    </div>
  );
}

export default App;
