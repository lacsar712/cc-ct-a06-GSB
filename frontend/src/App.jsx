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
  saveRange,
  setSession,
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
  if (raw.indexOf("/review") === 0) return { name: "review", id: null };
  return { name: "desk", id: null };
}

function App() {
  const [user, setUser] = createSignal(getUser());
  const [rows, setRows] = createSignal([]);
  const [history, setHistory] = createSignal([]);
  const [range, setRange] = createSignal(null);
  const [detail, setDetail] = createSignal(null);
  const [route, setRoute] = createSignal(readHash());
  const [error, setError] = createSignal("");
  const [notice, setNotice] = createSignal("");
  const [loading, setLoading] = createSignal(false);

  const [loginUser, setLoginUser] = createSignal("machinist");
  const [loginPass, setLoginPass] = createSignal("machine123456");

  const [toolCode, setToolCode] = createSignal("");
  const [offsetUm, setOffsetUm] = createSignal("");

  const [lowerLimit, setLowerLimit] = createSignal("");
  const [upperLimit, setUpperLimit] = createSignal("");
  const [savingRange, setSavingRange] = createSignal(false);

  const [correctingId, setCorrectingId] = createSignal(null);
  const [correctValue, setCorrectValue] = createSignal("");

  function goDesk() {
    location.hash = "#/";
  }

  function goReview() {
    location.hash = "#/review";
  }

  function goDetail(id) {
    location.hash = `#/detail/${id}`;
  }

  function flash(message) {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 4000);
  }

  async function loadRange() {
    const data = await fetchRange();
    setRange(data);
    setLowerLimit(String(data.lower_limit));
    setUpperLimit(String(data.upper_limit));
  }

  async function loadRows() {
    setRows(await fetchSubmissions());
  }

  async function loadHistory() {
    setHistory(await fetchHistory());
  }

  async function loadDetail(id) {
    setLoading(true);
    setError("");
    try {
      setDetail(await fetchSubmission(id));
    } catch (e) {
      setError(e.message);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadAll() {
    setError("");
    try {
      await Promise.all([loadRange(), loadRows(), loadHistory()]);
    } catch (e) {
      setError(e.message);
    }
  }

  onMount(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    if (user()) {
      if (route().name === "detail") loadDetail(route().id);
      else loadAll();
    }
    return () => window.removeEventListener("hashchange", onHash);
  });

  createEffect(() => {
    const r = route();
    if (!user()) return;
    if (r.name === "detail" && r.id) loadDetail(r.id);
    else loadAll();
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
      goDesk();
      await loadAll();
    } catch (err) {
      setError(err.message);
    }
  }

  function handleLogout() {
    clearSession();
    setUser(null);
    setRows([]);
    setHistory([]);
    setRange(null);
    setDetail(null);
    goDesk();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      // 表单入口：规则在后端闭区间校验，越界退回同一套规则文案
      await createSubmission(toolCode(), offsetUm());
      setToolCode("");
      setOffsetUm("");
      flash("交单成功，刀补原文已记入履历");
      await Promise.all([loadRows(), loadHistory()]);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSaveRange(e) {
    e.preventDefault();
    setError("");
    const lower = Number(lowerLimit());
    const upper = Number(upperLimit());
    if (!Number.isInteger(lower) || !Number.isInteger(upper)) {
      setError("上下限必须是整数（微米）");
      return;
    }
    setSavingRange(true);
    try {
      const data = await saveRange(lower, upper);
      setRange(data);
      flash(`量程区间已更新为闭区间 [${data.lower_limit}, ${data.upper_limit}]`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingRange(false);
    }
  }

  function startCorrect(row) {
    setCorrectingId(row.id);
    setCorrectValue(String(row.offset_um));
    setError("");
  }

  function cancelCorrect() {
    setCorrectingId(null);
    setCorrectValue("");
  }

  async function handleCorrect(id) {
    setError("");
    try {
      await correctSubmission(id, correctValue());
      cancelCorrect();
      flash("改正成功：单据数字已更新，旧履历原文保持不动");
      await Promise.all([loadRows(), loadHistory()]);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div class="page">
      <header class="topbar">
        <div class="brand">
          <h1>数控刀补量程台</h1>
          <p class="hint">
            刀补数值只能落在操作员设定的闭区间内；越界交单一律退回。成功交单即把刀补原文记入履历，
            事后改正单据数字时履历旧值不动，可用履历与单据对照验收。
          </p>
        </div>
        <Show when={user()}>
          <nav class="topnav">
            <a
              href="#/"
              class={route().name === "desk" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goDesk();
              }}
            >
              量程台
            </a>
            <a
              href="#/review"
              class={route().name === "review" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                goReview();
              }}
            >
              复核总览
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
            <p class="hint">操作员 machinist / machine123456；复核员 auditor / audit123456（区间与履历只读）</p>
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

        <Show when={route().name === "desk"}>
          {/* 区间设置：操作员可改，复核员只读 */}
          <section class="card">
            <h2>区间设置</h2>
            <Show when={range()} fallback={<p class="hint">加载中…</p>}>
              {(r) => (
                <>
                  <form onSubmit={handleSaveRange} class="form inline">
                    <label>
                      下限（微米，含）
                      <input
                        type="number"
                        value={lowerLimit()}
                        onInput={(e) => setLowerLimit(e.currentTarget.value)}
                        disabled={!user().can_write}
                        required
                      />
                    </label>
                    <label>
                      上限（微米，含）
                      <input
                        type="number"
                        value={upperLimit()}
                        onInput={(e) => setUpperLimit(e.currentTarget.value)}
                        disabled={!user().can_write}
                        required
                      />
                    </label>
                    <Show when={user().can_write}>
                      <button type="submit" disabled={savingRange()}>
                        {savingRange() ? "保存中…" : "保存区间"}
                      </button>
                    </Show>
                  </form>
                  <p class="rule">{r().rule}</p>
                  <Show when={!user().can_write}>
                    <p class="hint">复核员可查看区间与履历，但不能修改上下限。</p>
                  </Show>
                  <Show when={r().updated_by}>
                    <p class="hint">
                      最近由 {r().updated_by} 于 {new Date(r().updated_at).toLocaleString()} 设定
                    </p>
                  </Show>
                </>
              )}
            </Show>
          </section>

          {/* 交单栏：仅操作员；越界时按同一套规则退回 */}
          <Show when={user().can_write}>
            <section class="card">
              <h2>交单栏</h2>
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
                  刀补（微米）
                  <input
                    type="number"
                    value={offsetUm()}
                    onInput={(e) => setOffsetUm(e.currentTarget.value)}
                    required
                  />
                </label>
                <button type="submit">交单</button>
              </form>
              <Show when={range()}>
                <p class="rule">交单规则：{range().rule}</p>
              </Show>
            </section>
          </Show>

          {/* 履历区：刀补原文快照，可与单据现值对照验收 */}
          <section class="card">
            <h2>履历区</h2>
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>单据</th>
                  <th>刀具</th>
                  <th>动作</th>
                  <th>履历刀补原文</th>
                  <th>单据现值</th>
                  <th>对照</th>
                  <th>操作员</th>
                </tr>
              </thead>
              <tbody>
                <For each={history()}>
                  {(h) => (
                    <tr>
                      <td>{new Date(h.created_at).toLocaleString()}</td>
                      <td>
                        <a
                          href={`#/detail/${h.submission_id}`}
                          onClick={(e) => {
                            e.preventDefault();
                            goDetail(h.submission_id);
                          }}
                        >
                          #{h.submission_id}
                        </a>
                      </td>
                      <td>{h.tool_code}</td>
                      <td>{h.action_label}</td>
                      <td class="mono">{h.offset_text}</td>
                      <td class="mono">{h.current_offset_um}</td>
                      <td>
                        <Show
                          when={h.matches_current}
                          fallback={<span class="badge changed">已改正</span>}
                        >
                          <span class="badge same">一致</span>
                        </Show>
                      </td>
                      <td>{h.operator || "—"}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!history().length}>
              <p class="hint">暂无履历</p>
            </Show>
            <p class="hint">
              履历只追加、不修改：每条记录保存交单/改正当时的刀补原文；单据数字事后被改正时，旧履历保持不动。
            </p>
          </section>
        </Show>

        <Show when={route().name === "review"}>
          <section class="card">
            <div class="toolbar">
              <h2>复核列表</h2>
              <button
                type="button"
                class="ghost"
                onClick={() => Promise.all([loadRows(), loadHistory()]).catch((e) => setError(e.message))}
              >
                刷新
              </button>
            </div>
            <Show when={range()}>
              <p class="rule">当前{range().rule}</p>
            </Show>
            <table>
              <thead>
                <tr>
                  <th>刀具</th>
                  <th>刀补 µm</th>
                  <th>状态</th>
                  <th>结论</th>
                  <th>提交时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr>
                      <td>{row.tool_code}</td>
                      <td class="mono">
                        <Show
                          when={correctingId() === row.id}
                          fallback={row.offset_um}
                        >
                          <input
                            type="number"
                            value={correctValue()}
                            onInput={(e) => setCorrectValue(e.currentTarget.value)}
                          />
                        </Show>
                      </td>
                      <td>{statusLabel[row.status] || row.status}</td>
                      <td class={row.verdict === "合格" ? "pass" : row.verdict === "超差" ? "fail" : ""}>
                        {row.verdict || "—"}
                      </td>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td class="row-actions">
                        <Show
                          when={correctingId() === row.id}
                          fallback={
                            <>
                              <button type="button" class="ghost" onClick={() => goDetail(row.id)}>
                                详情
                              </button>
                              <Show when={user().can_write}>
                                <button type="button" class="ghost" onClick={() => startCorrect(row)}>
                                  改正
                                </button>
                              </Show>
                            </>
                          }
                        >
                          <button type="button" onClick={() => handleCorrect(row.id)}>
                            确认改正
                          </button>
                          <button type="button" class="ghost" onClick={cancelCorrect}>
                            取消
                          </button>
                        </Show>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
            <Show when={!rows().length}>
              <p class="hint">暂无记录</p>
            </Show>
          </section>
        </Show>

        <Show when={route().name === "detail"}>
          <section class="card">
            <div class="toolbar">
              <h2>刀补详情</h2>
              <button type="button" class="ghost" onClick={goDesk}>
                返回量程台
              </button>
            </div>
            <Show when={detail()} fallback={<p class="hint">{loading() ? "加载中…" : "未找到记录"}</p>}>
              {(d) => (
                <div class="detail-grid">
                  <p>编号：{d().id}</p>
                  <p>刀具：{d().tool_code}</p>
                  <p>刀补 µm：{d().offset_um}</p>
                  <p>状态：{statusLabel[d().status] || d().status}</p>
                  <p class={d().verdict === "合格" ? "pass" : d().verdict === "超差" ? "fail" : ""}>
                    结论：{d().verdict || "—"}
                  </p>
                  <p>提交时间：{new Date(d().created_at).toLocaleString()}</p>
                  <p>
                    复核时间：
                    {d().reviewed_at ? new Date(d().reviewed_at).toLocaleString() : "—"}
                  </p>
                  <p class="hint">该单据各次交单/改正的刀补原文见「量程台 → 履历区」，可与本页现值对照验收。</p>
                </div>
              )}
            </Show>
          </section>
        </Show>
      </Show>
    </div>
  );
}

export default App;
